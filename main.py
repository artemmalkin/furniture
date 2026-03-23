import os
import sqlite3
import smtplib
from email.mime.text import MIMEText
from datetime import datetime

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

DB_NAME = "orders.db"

app = FastAPI()
templates = Jinja2Templates(directory="templates")


# ---------------------------
# БАЗА ДАННЫХ
# ---------------------------
def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_name TEXT NOT NULL,
            client_email TEXT NOT NULL,
            phone TEXT,
            status TEXT NOT NULL DEFAULT 'Новый',
            comment TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


init_db()


# ---------------------------
# EMAIL
# ---------------------------
def send_email(to_email: str, subject: str, body: str):
    """
    Настрой SMTP через переменные окружения:
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM
    """
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    smtp_from = os.getenv("SMTP_FROM", smtp_user)

    if not smtp_host or not smtp_user or not smtp_password:
        print("SMTP не настроен. Письмо не отправлено.")
        print(f"TO: {to_email}\nSUBJECT: {subject}\nBODY:\n{body}")
        return

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = smtp_from
    msg["To"] = to_email

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_from, [to_email], msg.as_string())


# ---------------------------
# СТРАНИЦА СПИСКА ЗАКАЗОВ
# ---------------------------
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    conn = get_connection()
    orders = conn.execute(
        "SELECT * FROM orders ORDER BY id DESC"
    ).fetchall()
    conn.close()
    print(templates.get_template(
        "index.html",
        {
            "request": request,
            "orders": orders,
        }
    ))
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "orders": orders,
        }
    )


# ---------------------------
# ДОБАВЛЕНИЕ ЗАКАЗА
# ---------------------------
@app.post("/orders/add")
def add_order(
    client_name: str = Form(...),
    client_email: str = Form(...),
    phone: str = Form(""),
    comment: str = Form("")
):
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO orders (client_name, client_email, phone, status, comment, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            client_name,
            client_email,
            phone,
            "Новый",
            comment,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    )
    conn.commit()
    conn.close()

    return RedirectResponse(url="/", status_code=303)


# ---------------------------
# СМЕНА СТАТУСА + УВЕДОМЛЕНИЕ
# ---------------------------
@app.post("/orders/{order_id}/status")
def change_status(order_id: int, status: str = Form(...)):
    conn = get_connection()
    order = conn.execute(
        "SELECT * FROM orders WHERE id = ?",
        (order_id,)
    ).fetchone()

    if not order:
        conn.close()
        return RedirectResponse(url="/", status_code=303)

    conn.execute(
        "UPDATE orders SET status = ? WHERE id = ?",
        (status, order_id)
    )
    conn.commit()
    conn.close()

    subject = f"Изменился статус вашего заказа №{order_id}"
    body = (
        f"Здравствуйте, {order.client_name}!\n\n"
        f"Статус вашего заказа №{order_id} изменён на: {status}\n\n"
        f"Если у вас есть вопросы, свяжитесь с нами."
    )

    try:
        send_email(order.client_email, subject, body)
    except Exception as e:
        print("Ошибка отправки email:", e)

    return RedirectResponse(url="/", status_code=303)
