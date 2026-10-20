"""已撤入口的访问拦截；保留原业务实现和历史数据，不影响钱包查询。"""
from fastapi import HTTPException


async def require_operating_entries_enabled():
    raise HTTPException(403, "经营报表及客户应收、发货录入功能已停用")
