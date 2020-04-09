#-*-coding: utf-8 -*-
from bottle import request

class DemoHandler(object):
    def __init__(self, app):
        self.app = app
        self.app.route('/demo', self.hello, 'GET')

    #def hello(self, user): #强制从POST中获取
    def hello(self): #自己从query_string中获取
        user = request.query.get('user', 'world')
        return 'hello %s!'%user

def registerHandler(app):
    return DemoHandler(app)
