/**
 * DN42 Search - 前端交互脚本
 */

(function() {
    'use strict';
    
    // 搜索建议（简单实现）
    const searchInput = document.querySelector('.search-input');
    if (searchInput) {
        // 可以在这里实现搜索建议功能
        searchInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                const form = this.closest('form');
                if (form) {
                    form.submit();
                }
            }
        });
    }
    
    // 结果页的额外交互
    const resultItems = document.querySelectorAll('.result-item');
    resultItems.forEach(function(item) {
        item.addEventListener('mouseenter', function() {
            this.style.background = '#fafafa';
        });
        item.addEventListener('mouseleave', function() {
            this.style.background = '';
        });
    });
    
    // 平滑滚动
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                e.preventDefault();
                target.scrollIntoView({
                    behavior: 'smooth'
                });
            }
        });
    });
    
})();
