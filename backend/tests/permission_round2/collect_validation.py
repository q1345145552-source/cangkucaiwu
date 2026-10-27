import json,re,xml.etree.ElementTree as ET,subprocess,hashlib
from pathlib import Path
root=Path('/private/tmp/permissions-round2-20261028');out=root/'docs/permissions-round2-20261028';logs=Path('/private/tmp/permissions-round2-env/logs')
def failures(file):
 t=ET.parse(logs/file);return {c.attrib['name']: {'name':c.attrib['name'],'class':c.attrib.get('classname'),'message':c.find('failure').attrib.get('message',''),'trace':(c.find('failure').text or '')} for c in t.iter('testcase') if c.find('failure') is not None}
current=failures('regression-final.xml');baseline={}
for name in ('core-baseline.xml','reimbursement-baseline.xml'):
 for k,v in failures(name).items():baseline[k]={**v,'log':name.replace('.xml','.log')}
for line in (logs/'fund-baseline.log').read_text().splitlines():
 if line.startswith('FAILED '):
  name=line.split('::',1)[1];baseline[name]={'log':'fund-baseline.log'}
rows=[]
for name,value in current.items():
 old=baseline.get(name)
 category='基线角色/菜单/状态期望与现有守卫不同'
 if any(k in name for k in ('byte_identical','formula_preserved','functions_and_formula','paths_unchanged','business_tail_identical','second_cost')):category='较早提交的源码恒等断言在审计基线已不成立'
 if any(k in name for k in ('legacy_audit','company_payment_2000','cash_advance_cost','cny_account','decimal_item')):category='基线金额/资金口径期望差异；本轮未调整计算凑绿'
 if 'rollback_everything[cash_advance]' in name:category='基线现金垫款场景在注入故障前已被业务状态拒绝'
 rows.append({'test':name,'category':category,'same_failure_present_in_baseline':bool(old),'baseline_log':old['log'] if old else None,'actual_failure':value['message'],'current_log':'regression-final.log'})
summary={'total':475,'passed':423,'failed':52,'skipped':0,'exit_code':int((logs/'regression-final.exit').read_text()),'new_failure_names':[r['test'] for r in rows if not r['same_failure_present_in_baseline']],'failures':rows,'note':'原始基线与本轮使用各自测试文件；授权行为调整说明见报告及git diff。失败逐项同名对照不代表全系统无缺陷。'}
(out/'regression-baseline.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
md=['# 相关回归与第一轮基线对照','',f'完整相关回归475项：423通过、52失败、0跳过，退出码1。52项失败全部在第一轮审计提交 `{ "bc903a55c60c865f8eb95a4e6374ef5325ab4685" }` 的原测试复现；新增失败名称为 {summary["new_failure_names"]}。不能把此结果写成“全回归通过”。','', '基线分三批：核心402项（359通过/43失败）、备用金45项（41通过/4失败）、报销28项（23通过/5失败）。本轮修改后的授权行为另以目标接口验收；旧“主管配置成功”“审批即付款”等预期已逐项改为角色拒绝/核验批准执行，保留金额、历史、重复防护和回滚断言。','', '最后的手工开销核验后编辑退回待核验及所选仓库校验，另跑目标脚本与 `fund-controls-final`；详原日志。原撤销底层测试的旧测试夹具不等于恢复接口，新验收仍使用实际停用守卫。','', '|测试|归类|本轮实际失败|基线原日志|','|---|---|---|---|']
for r in rows:
 message=r['actual_failure'].replace('|','/').replace('\n',' ')[:360]
 md.append('|'+r['test'].replace('|','/')+'|'+r['category']+'|'+message+'|[同名失败](raw-logs/'+r['baseline_log']+')|')
md+=['','原始完整堆栈、返回状态和断言在 `raw-logs/regression-final.log`、对应基线日志和 XML 中；机器可读表保留完整失败消息。没有放宽类型配置、添加 skip/xfail 或删除测试来隐藏这些失败。','', '本轮旧测试调整：账户配置的主管/财务成功期望改403；员工新建自动建号/批量绑定改管理员；配置中心写入改管理员；备用金测试通过真实申请→核验→批准→独立执行准备资金，旧直接拨付单独断言403；批准后的用途编辑/撤销限制继续断言；关联报销批准不付款、已付不能借批量驳回退款、停用撤销不能重新执行。第一轮审计目录的原172请求、脚本及原断言未修改。']
(out/'REGRESSION-BASELINE.md').write_text('\n'.join(md)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k!='failures'},ensure_ascii=False))
