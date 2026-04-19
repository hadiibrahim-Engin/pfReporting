/* =========================================================
   De-energization Assessment - Interactive Report JavaScript
   ========================================================= */

(function () {
    'use strict';

    /* ----------------------------------------------------------
       Table sorting (vanilla — works alongside DataTables on
       plain tables that have no DataTables id)
    ---------------------------------------------------------- */
    document.querySelectorAll('th[data-sort]').forEach(function (th) {
        th.addEventListener('click', function () {
            var table = th.closest('table');
            if (!table) return;
            /* Skip DataTables-managed tables */
            if (table.id && (table.id === 'dt-voltage' || table.id === 'dt-thermal' || table.id === 'dt-n1')) return;
            var tbody = table.querySelector('tbody');
            var rows  = Array.from(tbody.querySelectorAll('tr'));
            var idx   = Array.from(th.parentNode.children).indexOf(th);
            var type  = th.dataset.sort;
            var dir   = th.classList.contains('asc') ? -1 : 1;

            rows.sort(function (a, b) {
                var va = a.children[idx] ? a.children[idx].textContent.trim() : '';
                var vb = b.children[idx] ? b.children[idx].textContent.trim() : '';
                if (type === 'num') {
                    va = parseFloat(va.replace(',', '.')) || 0;
                    vb = parseFloat(vb.replace(',', '.')) || 0;
                }
                return va > vb ? dir : va < vb ? -dir : 0;
            });

            th.parentNode.querySelectorAll('th').forEach(function (t) {
                t.classList.remove('asc', 'desc');
            });
            th.classList.add(dir === 1 ? 'asc' : 'desc');
            rows.forEach(function (r) { tbody.appendChild(r); });
        });
    });

    /* ----------------------------------------------------------
       Filter: Only anomalies (violations / warnings)
    ---------------------------------------------------------- */
    function applyIssueFilter(tbody, active) {
        if (!tbody) return;
        tbody.querySelectorAll('tr').forEach(function (row) {
            if (active) {
                var hasIssue = row.querySelector('.badge-violation, .badge-warning');
                row.dataset.filterHidden = hasIssue ? '0' : '1';
            } else {
                row.dataset.filterHidden = '0';
            }
        });
        applyVisibility(tbody);
    }

    /* Expose for DataTables draw.dt hooks in report.html.j2 */
    window.applyIssueFilter = applyIssueFilter;

    document.querySelectorAll('.filter-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var section = btn.closest('section');
            var tbody   = section && section.querySelector('table tbody');
            if (!tbody) return;

            var labelDefault = btn.dataset.labelDefault || 'Only anomalies';
            var labelActive  = btn.dataset.labelActive  || 'Show all';
            var active = btn.classList.toggle('active');
            applyIssueFilter(tbody, active);
            btn.textContent = active ? labelActive : labelDefault;
        });
    });

    document.querySelectorAll('.filter-toggle').forEach(function (cb) {
        var section = cb.closest('section');
        var tbody   = section ? section.querySelector('table tbody') : null;
        if (tbody) {
            applyIssueFilter(tbody, cb.checked);
        }
        cb.addEventListener('change', function () {
            var sec2  = cb.closest('section');
            var body2 = sec2 ? sec2.querySelector('table tbody') : null;
            if (!body2) return;
            applyIssueFilter(body2, cb.checked);
        });
    });

    /* ----------------------------------------------------------
       Global live search
    ---------------------------------------------------------- */
    var searchInput = document.getElementById('global-search');
    var searchCount = document.getElementById('search-count');

    if (searchInput) {
        var debounceTimer;
        searchInput.addEventListener('input', function () {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(runSearch, 160);
        });
    }

    function runSearch() {
        var term = searchInput ? searchInput.value.trim().toLowerCase() : '';
        var total = 0, visible = 0;

        document.querySelectorAll('table tbody').forEach(function (tbody) {
            tbody.querySelectorAll('tr').forEach(function (row) {
                total++;
                if (term === '') {
                    row.dataset.searchHidden = '0';
                } else {
                    var text = row.textContent.toLowerCase();
                    row.dataset.searchHidden = text.includes(term) ? '0' : '1';
                }
                applyVisibility(null, row);
                if (row.style.display !== 'none') visible++;
            });
        });

        if (searchCount) {
            searchCount.textContent = term ? visible + ' / ' + total + ' rows' : '';
        }
    }

    function applyVisibility(tbody, singleRow) {
        var rows = singleRow
            ? [singleRow]
            : (tbody ? Array.from(tbody.querySelectorAll('tr')) : []);
        rows.forEach(function (row) {
            var hidden = row.dataset.filterHidden === '1'
                      || row.dataset.searchHidden === '1'
                      || row.dataset.sectionSearchHidden === '1';
            row.style.display = hidden ? 'none' : '';
        });
    }

    /* ----------------------------------------------------------
       Per-section search
    ---------------------------------------------------------- */
    document.querySelectorAll('.section-search').forEach(function (input) {
        var sectionId = input.dataset.section;
        var section = document.getElementById(sectionId);
        if (!section) return;

        input.addEventListener('input', function () {
            var q = input.value.trim().toLowerCase();
            section.querySelectorAll('tbody tr').forEach(function (row) {
                var text = row.textContent.toLowerCase();
                row.dataset.sectionSearchHidden = (!q || text.includes(q)) ? '0' : '1';
                applyVisibility(null, row);
            });
        });
    });

    /* ----------------------------------------------------------
       Heatmap toggle — uses Tailwind 'hidden' class
    ---------------------------------------------------------- */
    document.querySelectorAll('.hm-toggle-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var targetId = btn.dataset.target;
            var panel = document.getElementById(targetId);
            if (!panel) return;

            var isOpen = !panel.classList.contains('hidden');
            panel.classList.toggle('hidden', isOpen);
            btn.textContent = isOpen
                ? (btn.dataset.labelOpen  || 'Show heatmap')
                : (btn.dataset.labelClose || 'Hide heatmap');

            if (!isOpen && !panel.dataset.hmInit) {
                panel.dataset.hmInit = '1';
                initHeatmapPanel(panel);
            }
        });
    });

    function initHeatmapPanel(panel) {
        var raw = panel.dataset.hm;
        if (!raw) return;
        var data;
        try { data = JSON.parse(raw); } catch (e) { return; }

        buildElemSelector(panel, data);
        renderHeatmapFiltered(panel, data);

        panel.querySelectorAll('.hm-select-btn').forEach(function (sb) {
            sb.addEventListener('click', function () {
                var mode = sb.dataset.mode;
                panel.querySelectorAll('.hm-elem-selector input').forEach(function (cb) {
                    if (mode === 'all')           cb.checked = true;
                    else if (mode === 'none')     cb.checked = false;
                    else if (mode === 'critical') {
                        var dot = cb.parentNode.querySelector('.hm-cb-dot');
                        var st  = dot ? dot.dataset.status : 'ok';
                        cb.checked = (st === 'violation' || st === 'warning');
                    }
                });
                renderHeatmapFiltered(panel, data);
                updateHmInfo(panel);
            });
        });
    }

    function buildElemSelector(panel, data) {
        var container = panel.querySelector('.hm-elem-selector');
        if (!container) return;
        container.innerHTML = '';

        var order  = { violation: 0, warning: 1, ok: 2 };
        var sorted = data.rows.slice().sort(function (a, b) {
            return (order[a.status] || 2) - (order[b.status] || 2);
        });

        sorted.forEach(function (row) {
            var item = document.createElement('label');
            item.className = 'inline-flex items-center gap-1.5 text-xs bg-white border border-slate-200 rounded-lg px-2 py-1 cursor-pointer hover:border-blue-400 transition-colors';

            var cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.value = row.name;
            cb.checked = (row.status === 'violation' || row.status === 'warning');
            cb.addEventListener('change', function () {
                renderHeatmapFiltered(panel, data);
                updateHmInfo(panel);
            });

            var dot = document.createElement('span');
            dot.className = 'hm-cb-dot inline-block w-2 h-2 rounded-full flex-shrink-0';
            dot.dataset.status = row.status || 'ok';
            var dotColors = { ok: '#16a34a', warning: '#d97706', violation: '#dc2626' };
            dot.style.background = dotColors[row.status] || dotColors.ok;

            var lbl = document.createElement('span');
            lbl.textContent = row.name;
            lbl.className = 'text-slate-700';

            item.appendChild(cb);
            item.appendChild(dot);
            item.appendChild(lbl);
            container.appendChild(item);
        });

        updateHmInfo(panel);
    }

    function updateHmInfo(panel) {
        var info = panel.querySelector('.hm-info');
        if (!info) return;
        var total   = panel.querySelectorAll('.hm-elem-selector input').length;
        var checked = panel.querySelectorAll('.hm-elem-selector input:checked').length;
        info.textContent = checked + ' / ' + total + ' elements selected';
    }

    function renderHeatmapFiltered(panel, data) {
        var selected = new Set();
        panel.querySelectorAll('.hm-elem-selector input:checked').forEach(function (cb) {
            selected.add(cb.value);
        });

        var filteredRows = data.rows.filter(function (r) { return selected.has(r.name); });
        var renderArea   = panel.querySelector('.hm-render-area');
        if (!renderArea) return;
        renderArea.innerHTML = '';

        if (filteredRows.length === 0) {
            renderArea.innerHTML = '<p class="text-xs text-slate-400 py-2">No element selected.</p>';
            return;
        }

        var filteredData = { time: data.time, rows: filteredRows, unit: data.unit };
        renderHeatmap(renderArea, filteredData, data);
    }

    /* ----------------------------------------------------------
       Heatmap rendering (static [data-heatmap] and interactive panels)
    ---------------------------------------------------------- */
    document.querySelectorAll('[data-heatmap]').forEach(function (container) {
        var raw = container.dataset.heatmap;
        var hmData;
        try { hmData = JSON.parse(raw); } catch (e) { return; }
        renderHeatmap(container, hmData, hmData);
    });

    function heatColor(val, min, max) {
        if (val == null) return 'rgba(241,245,249,0.8)';
        var t = max > min ? (val - min) / (max - min) : 0;
        t = Math.max(0, Math.min(1, t));
        var c1 = [29, 78, 216];   /* blue-700 */
        var c2 = [147, 51, 234];  /* purple-600 */
        var c3 = [249, 115, 22];  /* orange-500 */

        function mix(a, b, tt) {
            return [
                Math.round(a[0] + (b[0] - a[0]) * tt),
                Math.round(a[1] + (b[1] - a[1]) * tt),
                Math.round(a[2] + (b[2] - a[2]) * tt),
            ];
        }

        var rgb = t < 0.5 ? mix(c1, c2, t * 2) : mix(c2, c3, (t - 0.5) * 2);
        return 'rgb(' + rgb[0] + ',' + rgb[1] + ',' + rgb[2] + ')';
    }

    function getUnitPrecision(unit) { return unit === '%' ? 8 : 4; }

    function renderHeatmap(container, displayData, fullData) {
        var refData       = fullData || displayData;
        var unitPrecision = getUnitPrecision(displayData.unit);
        var allVals       = refData.rows.flatMap(function (r) {
            return r.values.filter(function (v) { return v != null; });
        });
        var minVal = allVals.length ? Math.min.apply(null, allVals) : 0;
        var maxVal = allVals.length ? Math.max.apply(null, allVals) : 1;

        var table = document.createElement('table');
        table.className = 'heatmap-table';

        var step  = Math.max(1, Math.floor(displayData.time.length / 40));
        var thead = table.createTHead();
        var hr    = thead.insertRow();
        var th0   = document.createElement('th');
        th0.textContent = 'Element / Time [h]';
        hr.appendChild(th0);
        displayData.time.forEach(function (t, i) {
            var th = document.createElement('th');
            th.className = 'col-header';
            th.textContent = (i % step === 0)
                ? (typeof t === 'number' ? t.toFixed(1) : t)
                : '';
            hr.appendChild(th);
        });

        var tbody = table.createTBody();
        displayData.rows.forEach(function (row) {
            var tr  = tbody.insertRow();
            var td0 = tr.insertCell();
            td0.className   = 'row-label';
            td0.textContent = row.name;
            row.values.forEach(function (v) {
                var td = tr.insertCell();
                td.style.backgroundColor = heatColor(v, minVal, maxVal);
                td.title = v != null
                    ? Number(v).toFixed(unitPrecision) + ' ' + displayData.unit
                    : 'n/a';
            });
        });

        container.innerHTML = '';
        container.appendChild(table);

        /* Colour legend */
        var leg   = document.createElement('div');
        leg.style.cssText = 'display:flex;align-items:center;gap:8px;margin-top:8px;font-size:11px;color:#6b7280;';
        var legId = 'hm-leg-' + Math.random().toString(36).slice(2);
        leg.innerHTML = '<span>' + minVal.toFixed(unitPrecision) + ' ' + displayData.unit + '</span>'
            + '<canvas id="' + legId + '" width="160" height="12" style="border-radius:4px"></canvas>'
            + '<span>' + maxVal.toFixed(unitPrecision) + ' ' + displayData.unit + '</span>';
        container.appendChild(leg);
        var lgCanvas = document.getElementById(legId);
        if (lgCanvas) {
            var ctx  = lgCanvas.getContext('2d');
            var grad = ctx.createLinearGradient(0, 0, 160, 0);
            grad.addColorStop(0,   heatColor(minVal, minVal, maxVal));
            grad.addColorStop(0.5, heatColor((minVal + maxVal) / 2, minVal, maxVal));
            grad.addColorStop(1,   heatColor(maxVal, minVal, maxVal));
            ctx.fillStyle = grad;
            ctx.fillRect(0, 0, 160, 12);
        }
    }

    /* ----------------------------------------------------------
       Chart.js — initialization from window.__chartData
    ---------------------------------------------------------- */
    function initCharts() {
        if (window.__chartsInitialized) return;
        if (typeof Chart === 'undefined' || !window.__chartData) return;
        window.__chartsInitialized = true;

        if (typeof ChartZoom !== 'undefined') {
            Chart.register(ChartZoom);
        }

        var COLORS = [
            '#2563eb', '#dc2626', '#d97706', '#16a34a', '#7c3aed',
            '#0891b2', '#be185d', '#92400e', '#065f46', '#1e40af',
            '#b91c1c', '#b45309', '#166534', '#6d28d9', '#0e7490',
        ];

        function getColor(index) { return COLORS[index % COLORS.length]; }

        var commonOptions = {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { boxWidth: 12, font: { size: 11 } },
                    onClick: function (e, legendItem, legend) {
                        var index = legendItem.datasetIndex;
                        var meta  = legend.chart.getDatasetMeta(index);
                        meta.hidden = !meta.hidden;
                        legend.chart.update();
                    },
                },
                zoom: {
                    zoom:  { wheel: { enabled: true }, pinch: { enabled: true }, mode: 'x' },
                    pan:   { enabled: true, mode: 'x' },
                },
            },
            elements: {
                point: { radius: 0, hoverRadius: 4 },
                line:  { tension: 0.2, borderWidth: 1.5 },
            },
        };

        window.__chartData.forEach(function (cfg) {
            var canvas = document.getElementById(cfg.id);
            if (!canvas) return;

            var datasets = cfg.series.map(function (s, i) {
                return {
                    label: s.name,
                    data: s.values,
                    borderColor: getColor(i),
                    backgroundColor: getColor(i) + '22',
                    fill: false,
                };
            });

            var annotations = [];
            if (cfg.warn_hi != null) {
                annotations.push({
                    type: 'line', yMin: cfg.warn_hi, yMax: cfg.warn_hi,
                    borderColor: '#d97706', borderWidth: 1.5, borderDash: [4, 4],
                    label: { content: 'Warning ' + cfg.warn_hi + ' ' + cfg.unit, display: true, position: 'end', color: '#d97706', font: { size: 10 } },
                });
            }
            if (cfg.violation_hi != null) {
                annotations.push({
                    type: 'line', yMin: cfg.violation_hi, yMax: cfg.violation_hi,
                    borderColor: '#dc2626', borderWidth: 1.5, borderDash: [4, 4],
                    label: { content: 'Violation ' + cfg.violation_hi + ' ' + cfg.unit, display: true, position: 'end', color: '#dc2626', font: { size: 10 } },
                });
            }

            var valuePrecision = Number.isInteger(cfg.value_precision)
                ? cfg.value_precision
                : (cfg.variable === 'c:loading' ? 8 : 4);

            var options = JSON.parse(JSON.stringify(commonOptions));
            options.scales = {
                x: {
                    title: { display: true, text: 'Time [h]', font: { size: 11 } },
                    ticks: { maxTicksLimit: 12, font: { size: 10 } },
                },
                y: {
                    title: { display: true, text: cfg.unit, font: { size: 11 } },
                    ticks: {
                        font: { size: 10 },
                        callback: function (value) {
                            if (value == null || Number.isNaN(Number(value))) return value;
                            return Number(value).toFixed(valuePrecision);
                        },
                    },
                },
            };
            if (annotations.length > 0 && typeof Chart.registry.plugins.get('annotation') !== 'undefined') {
                options.plugins.annotation = { annotations: annotations };
            }

            options.plugins.tooltip = {
                callbacks: {
                    label: function (context) {
                        var dsLabel = context.dataset && context.dataset.label ? context.dataset.label + ': ' : '';
                        var val = context.parsed ? context.parsed.y : null;
                        if (val == null || Number.isNaN(val)) return dsLabel + 'n/a';
                        return dsLabel + Number(val).toFixed(valuePrecision) + ' ' + cfg.unit;
                    },
                },
            };

            /* Re-attach legend onClick after deep-clone */
            options.plugins.legend.onClick = commonOptions.plugins.legend.onClick;

            var chart = new Chart(canvas, {
                type: 'line',
                data: { labels: cfg.time, datasets: datasets },
                options: options,
            });

            /* Add "Hide all / Show all" button above chart */
            var card = canvas.closest('.bg-slate-50, .chart-wrapper');
            var cardParent = card ? card.parentElement : null;
            if (cardParent) {
                var ctrlBar = document.createElement('div');
                ctrlBar.className = 'flex justify-end mb-2';
                var hideBtn = document.createElement('button');
                hideBtn.className = 'text-xs px-3 py-1 border border-slate-200 rounded-lg text-slate-500 hover:border-blue-400 hover:text-blue-600 transition-colors bg-white';
                hideBtn.textContent = 'Hide all';
                hideBtn.addEventListener('click', function () {
                    var allHidden = chart.data.datasets.every(function (ds, i) {
                        return chart.getDatasetMeta(i).hidden;
                    });
                    chart.data.datasets.forEach(function (ds, i) {
                        chart.getDatasetMeta(i).hidden = !allHidden;
                    });
                    chart.update();
                    hideBtn.textContent = allHidden ? 'Hide all' : 'Show all';
                });
                ctrlBar.appendChild(hideBtn);
                cardParent.insertBefore(ctrlBar, card);
            }
        });
    }

    /* Expose initCharts for Alpine setTab() call */
    window.initCharts = initCharts;

    /* Initialize charts immediately if the timeseries section is visible */
    function setupChartInitTriggers() {
        var tsSection = document.getElementById('sec-timeseries');
        if (!tsSection) {
            initCharts();
            return;
        }

        if ('IntersectionObserver' in window) {
            var obs = new IntersectionObserver(function (entries) {
                entries.forEach(function (entry) {
                    if (entry.isIntersecting) { initCharts(); obs.disconnect(); }
                });
            }, { rootMargin: '200px' });
            obs.observe(tsSection);
        } else {
            initCharts();
        }
    }

    setupChartInitTriggers();

})();
