"""已执行付款的撤销入口停用；保留各模块原回滚实现。"""
from fastapi import Depends, HTTPException

from app.core.permissions import get_current_user


REVERSAL_DISABLED_MESSAGE = "撤销功能已停用 请用负数冲销记录处理"


async def reject_disabled_financial_reversal(_user=Depends(get_current_user)):
    # 仍要求有效登录；拦在角色校验、读取单据和任何回滚操作之前。
    raise HTTPException(status_code=400, detail=REVERSAL_DISABLED_MESSAGE)
