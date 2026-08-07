"""LINE Messaging API notification service"""
import httpx
from app.config import get_settings


async def send_line_message(user_id: str, message: str) -> bool:
    """Send LINE message to a user via LINE Messaging API push message"""
    settings = get_settings()
    if not settings.LINE_CHANNEL_ACCESS_TOKEN:
        return False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.line.me/v2/bot/message/push",
                headers={
                    "Authorization": f"Bearer {settings.LINE_CHANNEL_ACCESS_TOKEN}",
                    "Content-Type": "application/json",
                },
                json={
                    "to": user_id,
                    "messages": [{"type": "text", "text": message[:5000]}],
                },
                timeout=10,
            )
            return resp.status_code == 200
    except Exception:
        return False


async def send_multicast_message(user_ids: list[str], message: str) -> bool:
    """Send LINE message to multiple users"""
    settings = get_settings()
    if not settings.LINE_CHANNEL_ACCESS_TOKEN or not user_ids:
        return False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.line.me/v2/bot/message/multicast",
                headers={
                    "Authorization": f"Bearer {settings.LINE_CHANNEL_ACCESS_TOKEN}",
                    "Content-Type": "application/json",
                },
                json={
                    "to": user_ids,
                    "messages": [{"type": "text", "text": message[:5000]}],
                },
                timeout=10,
            )
            return resp.status_code == 200
    except Exception:
        return False


async def notify_user(user, message: str) -> bool:
    """Send notification to user if LINE bound"""
    if user and user.line_user_id:
        return await send_line_message(user.line_user_id, message)
    return False


# ---- Notification triggers ----
async def notify_expense_fund_alert(user, remaining: float, threshold: float):
    """备用金警戒线提醒"""
    await notify_user(user, f"⚡ 备用金警戒提醒：您的备用金余额为 ¥{remaining}，已低于警戒线 ¥{threshold}，请及时关注。")


async def notify_reimbursement_submitted(user, reviewer, amount: float):
    """报销待审批通知"""
    await notify_user(reviewer, f"📋 新的报销单待审批：{user.display_name} 提交了 ¥{amount} 的报销申请，请及时处理。")


async def notify_reimbursement_approved(user, amount: float):
    """报销审批通过通知"""
    await notify_user(user, f"✅ 您的报销单（¥{amount}）已审批通过，等待付款。")


async def notify_payment_completed(user, amount: float):
    """付款完成通知"""
    await notify_user(user, f"💰 付款完成：¥{amount} 已支付。")


async def notify_overdue_alert(user, customer_name: str, overdue_days: int, debt: float):
    """逾期提醒"""
    await notify_user(user, f"⚠️ 逾期预警：{customer_name} 已逾期 {overdue_days} 天，当前欠款 ¥{debt}，请及时催收。")


async def notify_group_order_deadline(user, item_name: str):
    """拼单截止提醒"""
    await notify_user(user, f"📦 拼单“{item_name}”即将截止，请尽快确认参与。")


async def notify_market_review(user, item_name: str):
    """商品审核通知"""
    await notify_user(user, f"🛒 商品“{item_name}”等待审核，请及时处理。")
