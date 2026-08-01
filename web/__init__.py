# -*- coding: utf-8 -*-
"""
Web 应用初始化
"""
from flask import Flask
from config import WEB_CONFIG


def create_app(search_engine=None):
    """创建 Flask 应用"""
    app = Flask(__name__)
    app.config['SECRET_KEY'] = WEB_CONFIG['secret_key']
    
    # 存储搜索引擎实例
    app.config['search_engine'] = search_engine
    
    # 注册蓝图
    from web.routes import bp as main_bp
    app.register_blueprint(main_bp)
    
    return app
