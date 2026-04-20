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
            if (table.id && (table.id === 'dt-voltage' || table.id === 'dt-thermal')) return;
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
        /* Skip DataTables-managed tables — handled by DT external search in report.html.j2 */
        if (section && section.querySelector('table[id^="dt-"]')) return;
        var tbody = section ? section.querySelector('table tbody') : null;
        if (tbody) {
            applyIssueFilter(tbody, cb.checked);
        }
        cb.addEventListener('change', function () {
            var sec2 = cb.closest('section');
            if (sec2 && sec2.querySelector('table[id^="dt-"]')) return;
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
    var _chartInstances = [];

    function _computeYLimits(series, fallbackSpan) {
        var min = Number.POSITIVE_INFINITY;
        var max = Number.NEGATIVE_INFINITY;

        series.forEach(function (s) {
            (s.values || []).forEach(function (v) {
                if (v == null) return;
                var val = Number(v);
                if (!Number.isFinite(val)) return;
                min = Math.min(min, val);
                max = Math.max(max, val);
            });
        });

        if (!Number.isFinite(min) || !Number.isFinite(max)) {
            return null;
        }

        var center  = (min + max) / 2;
        var rawSpan = max - min;

        /* Enforce a minimum readable span so Chart.js ticking stays stable
           when all values are nearly identical (tiny decimal differences).
           Floor: 0.1 % of |center| OR 1e-4 absolute, whichever is larger. */
        var minSpan = Math.max(
            Number.isFinite(center) ? Math.abs(center) * 0.001 : 0,
            1e-4,
            (fallbackSpan || 1e-6) * 10
        );
        var span = Math.max(rawSpan, minSpan);

        var pad  = span * 0.15;
        var yMin = center - span / 2 - pad;
        var yMax = center + span / 2 + pad;

        if (!Number.isFinite(yMin) || !Number.isFinite(yMax) || yMax <= yMin) {
            yMin = center - minSpan / 2;
            yMax = center + minSpan / 2;
            span = minSpan;
        }

        return {
            min: yMin,
            max: yMax,
            span: span,
        };
    }

    /* Returns how many decimal places are needed to distinguish adjacent ticks.
       Deliberately ignores data precision — ticks need only be readable. */
    function _computeTickPrecision(yLimits) {
        if (!yLimits) return 2;
        var span = Math.abs(yLimits.span);
        if (!Number.isFinite(span) || span <= 0) return 2;
        return Math.min(5, Math.max(0, Math.ceil(-Math.log10(span)) + 1));
    }

    function initCharts() {
        if (window.__chartsInitialized) return;
        if (typeof Chart === 'undefined' || !window.__chartData) return;
        window.__chartsInitialized = true;

        var COLORS = [
            '#2563eb', '#dc2626', '#d97706', '#16a34a', '#7c3aed',
            '#0891b2', '#be185d', '#92400e', '#065f46', '#1e40af',
            '#b91c1c', '#b45309', '#166534', '#6d28d9', '#0e7490',
        ];

        window.__chartData.forEach(function (cfg) {
            var canvas = document.getElementById(cfg.id);
            if (!canvas) return;

            var valuePrecision = Number.isInteger(cfg.value_precision)
                ? cfg.value_precision
                : (cfg.variable === 'c:loading' ? 8 : 4);
            var yLimits = _computeYLimits(cfg.series || [], cfg.variable === 'c:loading' ? 1e-8 : 1e-6);
            var tickPrecision = _computeTickPrecision(yLimits);

            /* Unit-based axis fallbacks when there is no finite data at all */
            var yFallbackMin = (cfg.unit === '%') ? 0 : (cfg.unit === 'p.u.') ? 0.8 : undefined;
            var yFallbackMax = (cfg.unit === '%') ? 120 : (cfg.unit === 'p.u.') ? 1.2 : undefined;

            var datasets = cfg.series.map(function (s, i) {
                return {
                    label: s.name,
                    data: (cfg.time || []).map(function (t, k) {
                        var raw = s.values[k];
                        var num = (raw == null) ? null : Number(raw);
                        return { x: t, y: (num !== null && Number.isFinite(num)) ? num : null };
                    }),
                    borderColor: COLORS[i % COLORS.length],
                    backgroundColor: COLORS[i % COLORS.length],
                    pointRadius: 0,
                    pointHitRadius: 8,
                    borderWidth: 2,
                    tension: 0.15,
                    spanGaps: false,
                };
            });

            var chart = new Chart(canvas, {
                type: 'line',
                data: { datasets: datasets },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: false,
                    parsing: true,
                    interaction: {
                        mode: 'index',
                        intersect: false,
                    },
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: {
                                usePointStyle: true,
                                pointStyle: 'line',
                                boxWidth: 12,
                                boxHeight: 3,
                                font: { size: 11 },
                            },
                        },
                        tooltip: {
                            callbacks: {
                                title: function (items) {
                                    if (!items.length) return '';
                                    return 'Time: ' + Number(items[0].parsed.x).toFixed(4) + ' h';
                                },
                                label: function (context) {
                                    var val = context.parsed.y;
                                    var vStr = val == null
                                        ? 'n/a'
                                        : Number(val).toFixed(valuePrecision) + ' ' + cfg.unit;
                                    return context.dataset.label + ': ' + vStr;
                                },
                            },
                        },
                        zoom: {
                            /* limits.y intentionally omitted: y-axis is not zoomable
                               (mode:'x'), and passing limits confuses some plugin
                               versions on resetZoom(), causing the axis to jump. */
                            zoom: {
                                wheel: { enabled: true },
                                pinch: { enabled: true },
                                mode: 'x',
                            },
                            pan: {
                                enabled: true,
                                mode: 'x',
                                threshold: 4,
                            },
                        },
                    },
                    scales: {
                        x: {
                            type: 'linear',
                            title: {
                                display: true,
                                text: 'Time [h]',
                            },
                            ticks: {
                                callback: function (value) {
                                    return Number(value).toFixed(2);
                                },
                            },
                        },
                        y: {
                            type: 'linear',
                            min: yLimits ? yLimits.min : yFallbackMin,
                            max: yLimits ? yLimits.max : yFallbackMax,
                            title: {
                                display: true,
                                text: cfg.unit,
                            },
                            ticks: {
                                maxTicksLimit: 8,
                                callback: function (value) {
                                    var num = Number(value);
                                    if (!Number.isFinite(num)) return '';
                                    return num.toFixed(tickPrecision);
                                },
                            },
                        },
                    },
                },
            });

            canvas.addEventListener('dblclick', function () {
                if (typeof chart.resetZoom === 'function') {
                    chart.resetZoom();
                }
            });

            var cardParent = canvas.parentElement;
            if (cardParent) {
                var ctrlBar = document.createElement('div');
                ctrlBar.className = 'flex justify-end mb-2';
                var hideBtn = document.createElement('button');
                hideBtn.className = 'text-xs px-3 py-1 border border-slate-200 rounded-lg text-slate-500 hover:border-blue-400 hover:text-blue-600 transition-colors bg-white';
                hideBtn.textContent = 'Hide all';
                var allHidden = false;
                hideBtn.addEventListener('click', function () {
                    allHidden = !allHidden;
                    chart.data.datasets.forEach(function (_, index) {
                        chart.setDatasetVisibility(index, !allHidden);
                    });
                    chart.update();
                    hideBtn.textContent = allHidden ? 'Show all' : 'Hide all';
                });
                ctrlBar.appendChild(hideBtn);
                cardParent.insertBefore(ctrlBar, canvas);
            }

            _chartInstances.push(chart);
        });
    }

    window.initCharts      = initCharts;
    window.initRadarChart  = initRadarChart;
    window.refreshCharts = function () {
        if (!window.__chartsInitialized) {
            initCharts();
            return;
        }
        _chartInstances.forEach(function (chart) {
            chart.resize();
        });
    };

    function setupChartInitTriggers() {
        var tsSection = document.getElementById('sec-timeseries');
        if (!tsSection) return;

        if ('IntersectionObserver' in window) {
            var obs = new IntersectionObserver(function (entries) {
                entries.forEach(function (entry) {
                    if (entry.isIntersecting) {
                        window.refreshCharts();
                        obs.disconnect();
                    }
                });
            }, { rootMargin: '200px' });
            obs.observe(tsSection);
        } else {
            window.refreshCharts();
        }
    }

    /* ----------------------------------------------------------
       Radar chart — System Health overview
    ---------------------------------------------------------- */
    function initRadarChart() {
        if (window.__radarInit) return;
        if (typeof Chart === 'undefined' || !window.__radarData) return;
        var canvas = document.getElementById('radar-health');
        if (!canvas) return;
        window.__radarInit = true;

        var d      = window.__radarData;
        var scores = d.scores || [];
        var minS   = scores.length ? Math.min.apply(null, scores) : 100;
        var clrFill   = minS >= 80 ? 'rgba(16,163,74,0.18)'  : minS >= 50 ? 'rgba(217,119,6,0.18)'  : 'rgba(220,38,38,0.18)';
        var clrBorder = minS >= 80 ? 'rgb(16,163,74)'         : minS >= 50 ? 'rgb(217,119,6)'         : 'rgb(220,38,38)';

        new Chart(canvas, {
            type: 'radar',
            data: {
                labels: d.labels || [],
                datasets: [{
                    label: 'Health',
                    data: scores,
                    backgroundColor: clrFill,
                    borderColor: clrBorder,
                    borderWidth: 2,
                    pointBackgroundColor: clrBorder,
                    pointRadius: 4,
                    pointHoverRadius: 6,
                }]
            },
            options: {
                responsive: false,
                animation: false,
                scales: {
                    r: {
                        min: 0,
                        max: 100,
                        ticks: {
                            stepSize: 25,
                            font: { size: 9 },
                            color: '#94a3b8',
                            backdropColor: 'transparent',
                        },
                        grid:        { color: 'rgba(148,163,184,0.2)' },
                        angleLines:  { color: 'rgba(148,163,184,0.3)' },
                        pointLabels: { font: { size: 10 }, color: '#475569' },
                    }
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: function (ctx) {
                                var i   = ctx.dataIndex;
                                var det = d.detail && d.detail[i] ? ' — ' + d.detail[i] : '';
                                return ctx.parsed.r.toFixed(1) + ' %' + det;
                            },
                        },
                    },
                },
            },
        });
    }

    function setupRadarInitTrigger() {
        /* On the multi-page stats page #sec-statistics doesn't exist (no Alpine tabs),
           so fall through and init immediately once Chart.js is available. */
        var target = document.getElementById('sec-statistics') || document.getElementById('radar-health');
        if (!target) return;

        if ('IntersectionObserver' in window) {
            var obs = new IntersectionObserver(function (entries) {
                entries.forEach(function (entry) {
                    if (entry.isIntersecting) { initRadarChart(); obs.disconnect(); }
                });
            }, { rootMargin: '200px' });
            obs.observe(target);
        } else {
            initRadarChart();
        }
    }

    setupChartInitTriggers();
    setupRadarInitTrigger();

})();
