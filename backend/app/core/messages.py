"""多语言消息对照表：中文 / 泰语 / 缅甸语。

前端通过请求头 X-Language（zh / th / my）告知当前语言，
后端据此返回对应语言的提示消息。新增劳工会用到的消息时在此表补充即可。
"""
from fastapi import Request

MESSAGES = {
    # 打卡相关
    "only_labor_can_clock": {
        "zh": "只有仓库劳工可以使用打卡功能",
        "th": "เฉพาะแรงงานคลังสินค้าเท่านั้นที่ลงเวลาได้",
        "my": "ဂိုဒေါင်အလုပ်သမားသာ အလုပ်ဝင်ချိန်မှတ်နိုင်သည်",
    },
    "invalid_session": {
        "zh": "无效的打卡时段",
        "th": "ช่วงเวลาลงเวลาไม่ถูกต้อง",
        "my": "အလုပ်ဝင်ချိန်အပိုင်း မမှန်ကန်ပါ",
    },
    "already_clocked": {
        "zh": "今日{label}已打卡",
        "th": "วันนี้{label}ลงเวลาแล้ว",
        "my": "ယနေ့ {label} မှတ်တမ်းတင်ပြီးပါပြီ",
    },
    "invalid_photo": {
        "zh": "打卡照片格式无效",
        "th": "รูปแบบภาพถ่ายไม่ถูกต้อง",
        "my": "ဓာတ်ပုံဖော်မတ် မမှန်ကန်ပါ",
    },
    "clock_in_success": {
        "zh": "{label}打卡成功",
        "th": "{label} ลงเวลาสำเร็จ",
        "my": "{label} အလုပ်ဝင်ချိန်မှတ်တမ်းတင်ပြီးပါပြီ",
    },
    "clock_in_success_late": {
        "zh": "{label}打卡成功（迟到，月底结算时扣款）",
        "th": "{label} ลงเวลาสำเร็จ (มาสาย หักตอนสิ้นเดือน)",
        "my": "{label} မှတ်တမ်းတင်ပြီး (နောက်ကျ၊ လကုန်တွင်ဖြတ်မည်)",
    },
    "no_permission": {
        "zh": "无权限",
        "th": "ไม่มีสิทธิ์",
        "my": "ခွင့်ပြုချက်မရှိပါ",
    },
    # 加班确认
    "overtime_only_labor": {
        "zh": "只有仓库劳工可以确认加班",
        "th": "เฉพาะแรงงานคลังสินค้าเท่านั้นที่ยืนยันโอทีได้",
        "my": "ဂိုဒေါင်အလုပ်သမားသာ အချိန်ပိုအတည်ပြုနိုင်သည်",
    },
    "overtime_confirm_success": {
        "zh": "加班确认成功，已挣 {amount} 泰铢",
        "th": "ยืนยันโอทีสำเร็จ ได้รับ {amount} บาท",
        "my": "အချိန်ပိုအတည်ပြုပြီး {amount} ဘတ်ရရှိသည်",
    },
    # 打卡时段名称
    "session_1": {"zh": "早上上班", "th": "กะเช้า", "my": "မနက်အလုပ်ဝင်ချိန်"},
    "session_2": {"zh": "中午休息结束", "th": "หมดพักเที่ยง", "my": "နေ့လယ်အနားယူပြီး"},
    "session_3": {"zh": "下午上班", "th": "กะบ่าย", "my": "နေ့လယ်ပိုင်းအလုပ်ဝင်ချိန်"},
    "session_4": {"zh": "下午下班", "th": "เลิกงาน", "my": "ညနေအလုပ်ဆင်းချိန်"},
}

_VALID_LANGS = ("th", "my", "zh")


def get_request_lang(request: Request) -> str:
    """从前端请求头读取当前语言，返回 zh / th / my。"""
    lang = request.headers.get("X-Language") or request.headers.get("Accept-Language") or ""
    lang = (lang.split(",")[0] or "").strip().lower()
    if lang.startswith("th"):
        return "th"
    if lang.startswith("my") or lang.startswith("bur"):
        return "my"
    return "zh"


def t(key: str, lang: str = "zh", **kwargs) -> str:
    """取某语言的文案，回退到中文；支持 {name} 占位符。"""
    if lang not in _VALID_LANGS:
        lang = "zh"
    entry = MESSAGES.get(key, {})
    text = entry.get(lang) or entry.get("zh") or key
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            pass
    return text


def session_label(session: int, lang: str = "zh") -> str:
    """打卡时段名称（本地化）。"""
    return t(f"session_{session}", lang)
