# -*- coding: utf-8 -*-
"""
Web 路由
"""
from flask import Blueprint, render_template, request, jsonify, current_app

bp = Blueprint('main', __name__)


@bp.route('/')
def index():
    """首页"""
    return render_template('index.html')


@bp.route('/search')
def search():
    """搜索页面"""
    query = request.args.get('q', '').strip()
    page = max(1, int(request.args.get('page', 1)))
    mode = request.args.get('mode', 'hybrid')
    page_size = 20
    
    engine = current_app.config['search_engine']
    
    if not query:
        return render_template('results.html', 
                             query='', 
                             results=[], 
                             total=0,
                             page=1,
                             page_size=page_size,
                             time_ms=0,
                             suggestion=None)
    
    offset = (page - 1) * page_size
    result = engine.search(query, limit=page_size, offset=offset, mode=mode)
    
    return render_template('results.html',
                         query=result['query'],
                         original_query=result.get('original_query', query),
                         results=result['results'],
                         total=result['total'],
                         page=result['page'],
                         page_size=result['page_size'],
                         time_ms=result['time_ms'],
                         suggestion=result.get('suggestion'),
                         corrections=result.get('corrections', []),
                         mode=mode)


@bp.route('/api/search')
def api_search():
    """搜索 API"""
    query = request.args.get('q', '').strip()
    limit = min(100, int(request.args.get('limit', 20)))
    offset = max(0, int(request.args.get('offset', 0)))
    mode = request.args.get('mode', 'hybrid')
    
    engine = current_app.config['search_engine']
    result = engine.search(query, limit=limit, offset=offset, mode=mode)
    
    return jsonify(result)


@bp.route('/api/stats')
def api_stats():
    """统计信息 API"""
    engine = current_app.config['search_engine']
    stats = engine.get_stats()
    return jsonify(stats)


@bp.route('/api/explain')
def api_explain():
    """得分解释 API"""
    query = request.args.get('q', '').strip()
    doc_id = request.args.get('doc_id', '')
    
    engine = current_app.config['search_engine']
    
    if not query or not doc_id:
        return jsonify({'error': 'Missing query or doc_id'}), 400
    
    explanation = engine.explain(query, doc_id)
    return jsonify(explanation)


@bp.route('/about')
def about():
    """关于页面"""
    return render_template('about.html')


@bp.route('/stats')
def stats():
    """统计页面"""
    engine = current_app.config['search_engine']
    stats = engine.get_stats()
    top_pages = engine.get_top_pages(20)
    return render_template('stats.html', stats=stats, top_pages=top_pages)
