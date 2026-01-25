// Мобильное меню
document.addEventListener('DOMContentLoaded', function() {
    const mobileMenuToggle = document.querySelector('.mobile-menu-toggle');
    const sidebar = document.querySelector('.sidebar');
    const backdrop = document.querySelector('.sidebar-backdrop');
    const appShell = document.querySelector('.app-shell');

    // Создаем backdrop если его нет
    if (!backdrop && sidebar) {
        const newBackdrop = document.createElement('div');
        newBackdrop.className = 'sidebar-backdrop';
        document.body.appendChild(newBackdrop);
        
        newBackdrop.addEventListener('click', function() {
            closeMobileMenu();
        });
        
        // Закрытие по ESC
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && sidebar && sidebar.classList.contains('show')) {
                closeMobileMenu();
            }
        });
    }

    function openMobileMenu() {
        if (sidebar) {
            sidebar.classList.add('show');
            const backdropEl = document.querySelector('.sidebar-backdrop');
            if (backdropEl) {
                backdropEl.classList.add('show');
            }
            document.body.style.overflow = 'hidden';
            if (mobileMenuToggle) {
                mobileMenuToggle.setAttribute('aria-expanded', 'true');
                mobileMenuToggle.setAttribute('aria-label', 'Закрыть меню');
            }
        }
    }

    function closeMobileMenu() {
        if (sidebar) {
            sidebar.classList.remove('show');
            const backdropEl = document.querySelector('.sidebar-backdrop');
            if (backdropEl) {
                backdropEl.classList.remove('show');
            }
            document.body.style.overflow = '';
            if (mobileMenuToggle) {
                mobileMenuToggle.setAttribute('aria-expanded', 'false');
                mobileMenuToggle.setAttribute('aria-label', 'Открыть меню');
            }
        }
    }

    // Открытие/закрытие меню
    if (mobileMenuToggle && sidebar) {
        mobileMenuToggle.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            if (sidebar.classList.contains('show')) {
                closeMobileMenu();
            } else {
                openMobileMenu();
            }
        });
        
        // Улучшение доступности
        mobileMenuToggle.addEventListener('touchstart', function(e) {
            e.preventDefault();
        });
    }

    // Закрытие меню при клике на ссылку в сайдбаре (только на мобильных)
    if (sidebar) {
        const sidebarLinks = sidebar.querySelectorAll('.nav-link');
        sidebarLinks.forEach(function(link) {
            link.addEventListener('click', function() {
                if (window.innerWidth <= 767) {
                    setTimeout(closeMobileMenu, 300); // Небольшая задержка для плавности
                }
            });
        });
    }

    // Закрытие меню при изменении размера окна (если перешли на десктоп)
    let resizeTimer;
    window.addEventListener('resize', function() {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(function() {
            if (window.innerWidth > 767) {
                closeMobileMenu();
            }
        }, 250);
    });
});

// Переключатель сайдбара (иконки/полный) для десктопа
document.addEventListener('DOMContentLoaded', function() {
    const layout = document.querySelector('.dashboard-layout');
    const sidebar = document.querySelector('.sidebar');
    const toggle = document.querySelector('.sidebar-toggle');
    if (layout && sidebar && toggle && window.innerWidth > 767) {
        toggle.addEventListener('click', function(e) {
            e.preventDefault();
            layout.classList.toggle('sidebar-collapsed');
            sidebar.classList.toggle('sidebar-open');
        });
    }
});

// Обеспечиваем, чтобы таблицы были оборачены в контейнер .table-responsive
document.addEventListener('DOMContentLoaded', function() {
    const tables = document.querySelectorAll('table:not(.table-responsive table)');
    
    tables.forEach(function(table) {
        if (!table.closest('.table-responsive')) {
            const tableContainer = document.createElement('div');
            tableContainer.className = 'table-responsive';
            table.parentNode.insertBefore(tableContainer, table);
            tableContainer.appendChild(table);
        }
    });
});

// Улучшение форм на мобильных устройствах
document.addEventListener('DOMContentLoaded', function() {
    // Предотвращаем зум при фокусе на input (iOS)
    const inputs = document.querySelectorAll('input[type="text"], input[type="email"], input[type="number"], input[type="tel"], input[type="password"], textarea, select');
    inputs.forEach(function(input) {
        if (input.style.fontSize === '' || parseInt(input.style.fontSize) < 16) {
            input.style.fontSize = '16px';
        }
    });
});
