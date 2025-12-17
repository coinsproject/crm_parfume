// Переключатель сайдбара (иконки/полный)
document.addEventListener('DOMContentLoaded', function() {
    const layout = document.querySelector('.dashboard-layout');
    const sidebar = document.querySelector('.sidebar');
    const toggle = document.querySelector('.sidebar-toggle');
    if (layout && sidebar && toggle) {
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
