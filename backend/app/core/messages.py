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
    # 请假（劳工提交）
    "leave_type_invalid": {"zh": "请假类型无效", "th": "ประเภทการลาไม่ถูกต้อง", "my": "ခွင့်အမျိုးအစား မမှန်ကန်ပါ"},
    "leave_duration_invalid": {"zh": "请假时长类型无效", "th": "ระยะเวลาลาไม่ถูกต้อง", "my": "ခွင့်ကြာချိန်အမျိုးအစား မမှန်ကန်ပါ"},
    "hours_invalid": {"zh": "小时数无效", "th": "จำนวนชั่วโมงไม่ถูกต้อง", "my": "နာရီအရေအတွက် မမှန်ကန်ပါ"},
    "please_enter_leave_hours": {"zh": "请填写请假小时数", "th": "กรุณาใส่จำนวนชั่วโมงลา", "my": "ခွင့်နာရီအရေအတွက်ဖြည့်ပါ"},
    "please_select_warehouse": {"zh": "请先选择仓库", "th": "กรุณาเลือกคลังสินค้าก่อน", "my": "ဂိုဒေါင်အရင်ရွေးပါ"},
    "employee_not_found_contact_admin": {"zh": "未找到您的员工档案，请联系管理员", "th": "ไม่พบประวัติพนักงานของคุณ กรุณาติดต่อผู้ดูแล", "my": "သင့်ဝန်ထမ်းမှတ်တမ်းမတွေ့ပါ၊ အက်ဒမင်ကိုဆက်သွယ်ပါ"},
    "invalid_date_format": {"zh": "日期格式错误", "th": "รูปแบบวันที่ไม่ถูกต้อง", "my": "ရက်စွဲဖော်မတ် မမှန်ကန်ပါ"},
    "leave_already_submitted": {"zh": "该日期已提交请假申请", "th": "วันที่นี้ได้ยื่นขอลาแล้ว", "my": "ဤရက်အတွက် ခွင့်တင်ပြီးပါပြီ"},
    "leave_submitted": {"zh": "请假申请已提交，等待审批", "th": "ยื่นขอลาแล้ว รออนุมัติ", "my": "ခွင့်လျှောက်လွှာတင်ပြီး အတည်ပြုချက်စောင့်ဆိုင်းပါ"},
    # 加班确认（劳工）
    "overtime_task_not_found": {"zh": "加班任务不存在", "th": "ไม่พบงานโอที", "my": "အချိန်ပိုလုပ်ငန်း မရှိပါ"},
    "overtime_not_assigned": {"zh": "您未被分配该加班任务", "th": "คุณไม่ได้รับมอบหมายงานโอทีนี้", "my": "ဤအချိန်ပိုလုပ်ငန်းတွင် သင့်ကိုမသတ်မှတ်ထားပါ"},
    "overtime_already_confirmed": {"zh": "您已确认过该加班任务", "th": "คุณยืนยันงานโอทีนี้แล้ว", "my": "ဤအချိန်ပိုလုပ်ငန်းကို အတည်ပြုပြီးပါပြီ"},
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
