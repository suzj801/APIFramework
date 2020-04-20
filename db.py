#-*-coding:utf-8 -*-
import redis
import rediscluster
from peewee import DatabaseProxy
from playhouse.pool import PooledMySQLDatabase

database_proxy = DatabaseProxy()

def get_RedisConnection(redis_server, redis_port=6379, redis_password=None, db=0):
    #redis连接单节点与集群不一样
    if isinstance(redis_server, basestring):
        return redis.Redis(connection_pool=redis.ConnectionPool(host=redis_server, port=redis_port, password=redis_password, db=0))
    if isinstance(redis_server, list):
        if len(redis_server) == 1:
            return redis.Redis(connection_pool=redis.ConnectionPool(host=redis_server[0],
                port=redis_port, password=redis_password, db=db))
        else:
            startup_nodes = []
            for _server in redis_server:
                _host, _port = _server.split(':')
                startup_nodes.append({'host': _host, 'port': _port})
            return rediscluster.RedisCluster(startup_nodes=startup_nodes, decode_responses=True, password=redis_password)
    raise Exception('no redis_server')

def get_MysqlConnection(db_host, db_port, db_user, db_password, db_name, max_connection=100, stale_timeout=60):
    database_proxy.initialize(PooledMySQLDatabase(host=db_host, port=db_port, user=db_user, password=db_password,
        database=db_name, max_connections=max_connection, stale_timeout=stale_timeout))
    return database_proxy