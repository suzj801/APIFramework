#-*-coding:utf-8-*-

import os
import sys
import db
import inspect
import logging
import traceback
import glob
import importlib
import handler
import json
from bottle import Bottle, request, PluginError
from ConfigParser import RawConfigParser

WORK_DIR = os.path.realpath(os.path.dirname(__file__))
HANDLER_DIR = os.path.join(WORK_DIR, 'handler')

logger = logging.getLogger('main')

def logging_error():
    message = 'uri: %s  body: %s, trace stack: %s'%(request.path, request.body.read(), traceback.format_exc())
    logger.critical(message)

class APIError(Exception):
    pass

class ParseArgs(object):
    name = 'parseArgs'
    api = 2

    def __init__(self):
        pass

    def setup(self, app):
        for other in app.plugins:
            if not isinstance(other, ParseArgs): continue
            if other.name == self.name:
                raise PluginError("conflicting plugin")

    def apply(self, callback, context):
        def wrapper(*args, **kwargs):
            try:
                func_args = context.config.get('func_args')
                func_ignore_args = context.config.get('func_ignore_args')
                if func_args:
                    for _arg in func_args:
                        if _arg == 'self': #排除self参数
                            continue
                        if _arg not in request.POST and _arg not in func_ignore_args:
                            raise APIError('EMPTY_PARAMETER_NAME:' + _arg)
                        if _arg in request.POST:
                            _arg_value = request.POST[_arg]
                            try:
                                _arg_value = _arg_value.decode('utf-8') ##统一unicode编码
                            except:
                                pass
                            kwargs[_arg] = _arg_value
                        else:
                            kwargs[_arg] = func_ignore_args[_arg]
                return return_success(callback(*args, **kwargs))
            except Exception as err:
                logging_error()
                err_msg = 'INTERNAL_ERROR'
                if isinstance(err, APIError): err_msg = str(err)
                return return_failed(err_msg)
        return wrapper

def return_success(value):
    return {'status': 'success', 'value': value}

def return_failed(err):
    return {'status': 'failed', 'info': err}

CONF_DEFAULTS = {
    'listen_port': 8000,
    'db_host': '127.0.0.1',
    'db_port': 3306,
    'db_name': 'api',
    'db_user': 'root',
    'db_password': '',
    'db_max_connections': 100,
    'db_stale_timeout': 60,
    'redis_server': '127.0.0.1',
    'redis_port': 6379,
    'redis_password': '',
    'debug': '0'
}

class APIFramework(Bottle):
    def __init__(self, conffile_path, conf_sec):
        super(APIFramework, self).__init__()
        conf = RawConfigParser(CONF_DEFAULTS)
        conf.read(conffile_path)
        self.listen_port = conf.getint(conf_sec, 'listen_port')
        #mysql
        self.db_host = conf.get(conf_sec, 'db_host')
        self.db_port = conf.getint(conf_sec, 'db_port')
        self.db_name = conf.get(conf_sec, 'db_name')
        self.db_user = conf.get(conf_sec, 'db_user')
        self.db_password = conf.get(conf_sec, 'db_password')
        db_max_connection = conf.getint(conf_sec, 'db_max_connections')
        db_stale_timeout = conf.getint(conf_sec, 'db_stale_timeout')
        #redis
        self.redis_server = conf.get(conf_sec, 'redis_server').split(',')
        self.redis_port = conf.getint(conf_sec, 'redis_port')
        self.redis_password = conf.get(conf_sec, 'redis_password')
        #debug
        self.debug = conf.getboolean(conf_sec, 'debug')
        #db/redis init
        self.db = db.get_MysqlConnection(self.db_host, self.db_port, self.db_user, self.db_password, self.db_name,
                                        db_max_connection, db_stale_timeout)
        self.redis_conn = db.get_RedisConnection(self.redis_server, self.redis_port, self.redis_password)
        #errors
        self.error_handler[404] = self.NotFoundError
        self.add_hook('before_request', self.before_request)
        self.add_hook('after_request', self.after_request)
        #install plugins
        self.install(ParseArgs())
        #register handler
        self.loadHandlers(True)
        #install self handler
        if self.debug:
            Bottle.route(self, '/reloadhandlers', ['GET', 'POST'], self.loadHandlers)
        else:
            Bottle.route(self, '/reloadhandlers', 'POST', self.loadHandlers)

    def loadHandlers(self, continue_on_error=False):
        if WORK_DIR not in sys.path:
            sys.path.insert(0, WORK_DIR)
        EXTENSION = '.py' if os.path.isfile(os.path.join(HANDLER_DIR, '__init__.py')) else '.pyc'
        #如果存在__init__.py则全部重载py文件, 否则重载pyc文件
        for handler_file in glob.glob(os.path.join(HANDLER_DIR, '*'+EXTENSION)):
            if handler_file in ['__init__.py', '__init__.pyc']:
                continue
            handler_name = os.path.basename(handler_file)[:-len(EXTENSION)]
            if not handler_name:
                continue
            try:
                if sys.modules.get('handler.%s'%handler_name):
                    print('reload module handler.%s'%handler_name)
                    _module = reload(getattr(handler, handler_name))
                else:
                    _module = importlib.import_module('.%s'%handler_name, 'handler')
            except Exception as e:
                print('register handler %s error: %s'%(handler_name, e))
                continue
            if hasattr(_module, 'registerHandler'):
                try:
                    getattr(_module, 'registerHandler')(self)
                    print('registered handler:%s'%_module)
                except Exception as e:
                    print('register handler %s error: %s'%(handler_name, e))
                    traceback.print_exc()
                    if not continue_on_error:
                        raise APIError('HANDLER_REGISTER_FAILED:' + handler_name)

    def route(self, path, callback, method='POST', register_action=False, description=''):
        if register_action:
            _path = path.lstrip('/').lower()
            if not db.APIAction.get_or_none(action=_path):
                db.APIAction.create(action=_path, action_desc=description)
        #抓取callback需要哪些参数, 在plugin中直接从POST中获取并在call method的时候赋予
        argspec = inspect.getargspec(callback)
        func_args = argspec.args  #method的所有参数
        #获取参数中哪些有默认值
        func_ignore_args = dict(zip(reversed(argspec.args), reversed(argspec.defaults))) if argspec.defaults else {}
        Bottle.route(self, path, method, callback, func_args=func_args, func_ignore_args=func_ignore_args)

    def NotFoundError(self, res):
        return 'URL_NOT_EXISTS'

    def run_server(self, host='0.0.0.0', port=None):
        self.run(host=host, port=port or self.listen_port, debug=self.debug)

    def get_remote_addr(self):
        return request.remote_addr or request.headers.get('X-Real-IP') #从反向代理拿取IP

    def before_request(self):
        pass

    def after_request(self):
        pass

if __name__ == '__main__':
    api = APIFramework('test.conf', 'development')
    api.run_server()