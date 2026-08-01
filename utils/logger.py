# -*- coding: utf-8 -*-
"""
日志工具模块
"""
import logging
import logging.handlers
import sys
from config import LOG_CONFIG


def setup_logger(name='dn42-search'):
    """设置日志记录器"""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, LOG_CONFIG['level']))
    
    # 避免重复添加 handler
    if logger.handlers:
        return logger
    
    # 格式化器
    formatter = logging.Formatter(LOG_CONFIG['format'])
    
    # 控制台 handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 文件 handler（轮转）
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            LOG_CONFIG['file'],
            maxBytes=LOG_CONFIG['max_bytes'],
            backupCount=LOG_CONFIG['backup_count'],
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        logger.warning(f"无法创建日志文件: {e}")
    
    return logger


def get_logger(name):
    """获取日志记录器"""
    return logging.getLogger(name)
