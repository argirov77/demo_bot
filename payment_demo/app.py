from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from urllib.parse import urlencode

app = FastAPI(title="DemoPay")
app.mount("/static", StaticFiles(directory="payment_demo/payments"), name="static")

@app.get("/pay", response_class=HTMLResponse)
async def pay(order_id: int, amount: int, currency: str = "BGN", return_url: str | None = None):
    with open("payment_demo/payments/payment.html", "r", encoding="utf-8") as f:
        html = f.read()
    html = html.replace("{{AMOUNT}}", f"{amount/100:.2f} {currency}") \
               .replace("{{ORDER_ID}}", str(order_id)) \
               .replace("{{RETURN_URL}}", return_url or "")
    return HTMLResponse(html)

@app.post("/pay/submit")
async def pay_submit(request: Request):
    form = await request.form()
    order_id = form.get("order_id")
    action = form.get("action")
    return_url = form.get("return_url")
    status = "paid" if action == "success" else ("failed" if action == "fail" else "canceled")
    if return_url:
        q = urlencode({"status": status, "order_id": order_id})
        return RedirectResponse(url=f"{return_url}?{q}", status_code=302)
    if status == "paid":
        return RedirectResponse(url="/static/result_success.html", status_code=302)
    return RedirectResponse(url="/static/result_fail.html", status_code=302)
