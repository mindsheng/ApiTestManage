import json
from flask import jsonify, request
from . import api
from app.models import Project, Task, CaseSet, Case, db
from ..util.custom_decorator import login_required
from app import scheduler
from ..util.http_run import RunCase
from ..util.utils import change_cron, auto_num
from ..util.email.SendEmail import SendEmail
from ..util.report.report import render_html_report
from ..util.global_variable import TEMP_REPORT
import datetime


def aps_test(project_name, case_ids, send_address=None, send_password=None, task_to_address=None):
    project_id = Project.query.filter_by(name=project_name).first().id
    d = RunCase(project_id)
    jump_res = d.run_case(d.get_case_test(case_ids))
    d.build_report(jump_res, case_ids)
    res = json.loads(jump_res)

    if send_address:
        task_to_address = task_to_address.split(',')
        file = render_html_report(res,
                                  html_report_name='{}接口自动化测试报告'.format(
                                      datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')),
                                  html_report_template=r'{}/extent_report_template.html'.format(TEMP_REPORT),
                                  data_or_report=False)
        s = SendEmail(send_address, send_password, task_to_address, file)
        s.send_email()
    return d


@api.route('/task/run', methods=['POST'])
@login_required
def run_task():
    """ 单次运行任务 """
    data = request.json
    ids = data.get('id')
    _data = Task.query.filter_by(id=ids).first()
    case_ids = []
    if len(json.loads(_data.case_id)) != 0:
        case_ids += [i['id'] for i in json.loads(_data.case_id)]
    else:
        if len(json.loads(_data.case_id)) == 0 and len(json.loads(_data.set_id)) == 0:
            project_id = Project.query.filter_by(name=_data.project_name).first().id
            _set_ids = [_set.id for _set in
                        CaseSet.query.filter_by(project_id=project_id).order_by(CaseSet.num.asc()).all()]
        else:
            _set_ids = [i['id'] for i in json.loads(_data.set_id)]
        for set_id in _set_ids:
            for case_data in Case.query.filter_by(case_set_id=set_id).order_by(Case.num.asc()).all():
                case_ids.append(case_data.id)
    project_name = Project.query.filter_by(id=_data.project_id).first().name
    result = aps_test(project_name, case_ids)

    return jsonify({'msg': '测试成功', 'status': 1, 'data': {'report_id': result.new_report_id}})


@api.route('/task/start', methods=['POST'])
@login_required
def start_task():
    """ 任务开启 """
    data = request.json
    ids = data.get('id')
    _data = Task.query.filter_by(id=ids).first()

    config_time = change_cron(_data.task_config_time)
    case_ids = []
    if len(json.loads(_data.case_id)) != 0:
        case_ids += [i['id'] for i in json.loads(_data.case_id)]
    else:
        if len(json.loads(_data.case_id)) == 0 and len(json.loads(_data.set_id)) == 0:
            project_id = Project.query.filter_by(name=_data.project_name).first().id
            _set_ids = [_set.id for _set in
                        CaseSet.query.filter_by(project_id=project_id).order_by(CaseSet.num.asc()).all()]
        else:
            _set_ids = [i['id'] for i in json.loads(_data.set_id)]
        for set_id in _set_ids:
            for case_data in Case.query.filter_by(case_set_id=set_id).order_by(Case.num.asc()).all():
                case_ids.append(case_data.id)
    # scheduler.add_job(str(ids), aps_test, trigger='cron', args=['asd'], **config_time)
    project_name = Project.query.filter_by(id=_data.project_id).first().name
    scheduler.add_job(func=aps_test, trigger='cron',
                      args=[project_name, case_ids, _data.task_send_email_address, _data.email_password,
                            _data.task_to_email_address],
                      id=str(ids), **config_time)  # 添加任务
    _data.status = '启动'
    db.session.commit()

    return jsonify({'msg': '启动成功', 'status': 1})


@api.route('/task/add', methods=['POST'])
@login_required
def add_task():
    """ 任务添加、修改 """
    data = request.json
    project_name = data.get('projectName')
    if not project_name:
        return jsonify({'msg': '请选择项目', 'status': 0})
    project_id = Project.query.filter_by(name=project_name).first().id
    set_ids = data.get('setIds')
    case_ids = data.get('caseIds')
    task_id = data.get('id')
    num = auto_num(data.get('num'), Task, project_id=project_id)
    name = data.get('name')
    task_type = 'cron'
    to_email = data.get('toEmail')
    send_email = data.get('sendEmail')
    password = data.get('password')
    # 0 0 1 * * *
    if not (not to_email and not send_email and not password) and not (to_email and send_email and password):
        return jsonify({'msg': '发件人、收件人、密码3个必须都为空，或者都必须有值', 'status': 0})

    time_config = data.get('timeConfig')
    if len(time_config.strip().split(' ')) != 6:
        return jsonify({'msg': 'cron格式错误', 'status': 0})

    if task_id:
        old_task_data = Task.query.filter_by(id=task_id).first()
        if Task.query.filter_by(task_name=name).first() and name != old_task_data.task_name:
            return jsonify({'msg': '任务名字重复', 'status': 0})
        else:
            old_task_data.project_id = project_id
            old_task_data.set_id = json.dumps(set_ids)
            old_task_data.case_id = json.dumps(case_ids)
            old_task_data.task_name = name
            old_task_data.task_type = task_type
            old_task_data.task_to_email_address = to_email
            old_task_data.task_send_email_address = send_email
            old_task_data.email_password = password
            old_task_data.num = num
            if old_task_data.status != '创建' and old_task_data.task_config_time != time_config:
                scheduler.reschedule_job(str(task_id), trigger='cron', **change_cron(time_config))  # 修改任务
                old_task_data.status = '启动'

            old_task_data.task_config_time = time_config
            db.session.commit()
            return jsonify({'msg': '修改成功', 'status': 1})
    else:

        if Task.query.filter_by(task_name=name).first():
            return jsonify({'msg': '任务名字重复', 'status': 0})
        else:
            new_task = Task(task_name=name,
                            project_id=project_id,
                            set_id=json.dumps(set_ids),
                            case_id=json.dumps(case_ids),
                            email_password=password,
                            task_type=task_type,
                            task_to_email_address=to_email,
                            task_send_email_address=send_email,
                            task_config_time=time_config,
                            num=num)
            db.session.add(new_task)
            db.session.commit()
            return jsonify({'msg': '新建成功', 'status': 1})


@api.route('/task/edit', methods=['POST'])
@login_required
def edit_task():
    """ 返回待编辑任务信息 """
    data = request.json
    task_id = data.get('id')
    c = Task.query.filter_by(id=task_id).first()
    _data = {'num': c.num, 'task_name': c.task_name, 'task_config_time': c.task_config_time, 'task_type': c.task_type,
             'set_ids': json.loads(c.set_id), 'case_ids': json.loads(c.case_id),
             'task_to_email_address': c.task_to_email_address, 'task_send_email_address': c.task_send_email_address,
             'password': c.email_password}

    return jsonify({'data': _data, 'status': 1})


@api.route('/task/find', methods=['POST'])
@login_required
def find_task():
    """ 查找任务信息 """
    data = request.json
    project_name = data.get('projectName')
    project_id = Project.query.filter_by(name=project_name).first().id
    task_name = data.get('taskName')
    page = data.get('page') if data.get('page') else 1
    per_page = data.get('sizePage') if data.get('sizePage') else 10
    if task_name:
        _data = Task.query.filter_by(project_id=project_id).filter(Task.task_name.like('%{}%'.format(task_name))).all()
        total = len(_data)
        if not _data:
            return jsonify({'msg': '没有该任务', 'status': 0})
    else:
        tasks = Task.query.filter_by(project_id=project_id)
        pagination = tasks.order_by(Task.id.asc()).paginate(page, per_page=per_page, error_out=False)
        _data = pagination.items
        total = pagination.total
    task = [{'task_name': c.task_name, 'task_config_time': c.task_config_time,
             'id': c.id, 'task_type': c.task_type, 'status': c.status} for c in _data]
    return jsonify({'data': task, 'total': total, 'status': 1})


@api.route('/task/del', methods=['POST'])
@login_required
def del_task():
    """ 删除任务信息 """
    data = request.json
    ids = data.get('id')
    _edit = Task.query.filter_by(id=ids).first()
    if _edit.status != '创建':
        return jsonify({'msg': '请先移除任务', 'status': 0})

    db.session.delete(_edit)
    return jsonify({'msg': '删除成功', 'status': 1})


@api.route('/task/pause', methods=['POST'])
@login_required
def pause_task():
    """ 暂停任务 """
    data = request.json
    ids = data.get('id')
    _data = Task.query.filter_by(id=ids).first()
    _data.status = '暂停'
    scheduler.pause_job(str(ids))  # 添加任务
    db.session.commit()

    return jsonify({'msg': '暂停成功', 'status': 1})


@api.route('/task/resume', methods=['POST'])
@login_required
def resume_task():
    """ 恢复任务 """
    data = request.json
    ids = data.get('id')
    _data = Task.query.filter_by(id=ids).first()
    _data.status = '启动'
    scheduler.resume_job(str(ids))  # 添加任务
    db.session.commit()
    return jsonify({'msg': '恢复成功', 'status': 1})


@api.route('/task/remove', methods=['POST'])
@login_required
def remove_task():
    """ 移除任务 """
    data = request.json
    ids = data.get('id')
    _data = Task.query.filter_by(id=ids).first()
    scheduler.remove_job(str(ids))  # 添加任务
    _data.status = '创建'
    db.session.commit()
    return jsonify({'msg': '移除成功', 'status': 1})
