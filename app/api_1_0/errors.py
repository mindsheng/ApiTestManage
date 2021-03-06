from flask import jsonify, current_app, request
from . import api
import traceback


@api.app_errorhandler(404)
def page_not_found(e):
    # e = traceback.format_exc()
    current_app.logger.exception('404错误url:{}'.format(request.url))
    # response = jsonify({'error': 'not found','data':e})
    # response.status_code = 404
    return jsonify({'msg': '后台不存在此请求'})


@api.app_errorhandler(Exception)
def error_handler(e):
    # e = traceback.format_exc()
    current_app.logger.exception(traceback.format_exc())
    # response = jsonify({'error': 'not found','data':e})
    # response.status_code = 404
    return jsonify({'msg': '服务器异常，请查看返回的error信息，无法处理则联系管理员', 'status': 0, 'error': '{}'.format(traceback.format_exc())})
