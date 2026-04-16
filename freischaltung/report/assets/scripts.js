/* =========================================================
   Freischaltungsbewertung – Interaktives Report-JavaScript
   ========================================================= */

(function () {
    'use strict';

    /* ----------------------------------------------------------
       Tabellen-Sortierung
    ---------------------------------------------------------- */
    document.querySelectorAll('th[data-sort]').forEach(function (th) {
        th.addEventListener('click', function () {
            var table = th.closest('table');
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
       Filter: Nur Auffälligkeiten
    ---------------------------------------------------------- */
    document.querySelectorAll('.filter-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var section = btn.closest('section');
            var tbody   = section.querySelector('table tbody');
            if (!tbody) return;

            var active = btn.classList.toggle('active');
            tbody.querySelectorAll('tr').forEach(function (row) {
                if (active) {
                    var hasIssue = row.querySelector('.badge-verletzung, .badge-warnung');
                    row.dataset.filterHidden = hasIssue ? '0' : '1';
                } else {
                    row.dataset.filterHidden = '0';
                }
            });
            btn.textContent = active ? 'Alle anzeigen' : 'Nur Auffälligkeiten';
            applyVisibility(tbody);
        });
    });

    /* ----------------------------------------------------------
       Globale Live-Suche
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
            searchCount.textContent = term
                ? visible + ' / ' + total + ' Zeilen'
                : '';
        }
    }

    function applyVisibility(tbody, singleRow) {
        var rows = singleRow ? [singleRow] : (tbody ? Array.from(tbody.querySelectorAll('tr')) : []);
        rows.forEach(function (row) {
            var hidden = row.dataset.filterHidden === '1' || row.dataset.searchHidden === '1';
            row.style.display = hidden ? 'none' : '';
        });
    }

    /* ----------------------------------------------------------
       Chart.js – Initialisierung aus window.__chartData
    ---------------------------------------------------------- */
    if (typeof Chart === 'undefined' || !window.__chartData) return;

    // Register zoom plugin if available
    if (typeof ChartZoom !== 'undefined') {
        Chart.register(ChartZoom);
    }

    var COLORS = [
        '#2563eb', '#dc2626', '#d97706', '#16a34a', '#7c3aed',
        '#0891b2', '#be185d', '#92400e', '#065f46', '#1e40af',
        '#b91c1c', '#b45309', '#166534', '#6d28d9', '#0e7490',
    ];

    function getColor(index) {
        return COLORS[index % COLORS.length];
    }

    var commonOptions = {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
            legend: {
                position: 'bottom',
                labels: { boxWidth: 12, font: { size: 11 } },
            },
            zoom: {
                zoom: {
                    wheel: { enabled: true },
                    pinch: { enabled: true },
                    mode: 'x',
                },
                pan: {
                    enabled: true,
                    mode: 'x',
                },
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
                label: { content: 'Warnung ' + cfg.warn_hi + ' ' + cfg.unit, display: true,
                         position: 'end', color: '#d97706', font: { size: 10 } },
            });
        }
        if (cfg.violation_hi != null) {
            annotations.push({
                type: 'line', yMin: cfg.violation_hi, yMax: cfg.violation_hi,
                borderColor: '#dc2626', borderWidth: 1.5, borderDash: [4, 4],
                label: { content: 'Verletzung ' + cfg.violation_hi + ' ' + cfg.unit, display: true,
                         position: 'end', color: '#dc2626', font: { size: 10 } },
            });
        }

        var options = JSON.parse(JSON.stringify(commonOptions));
        options.scales = {
            x: {
                title: { display: true, text: 'Zeit [h]', font: { size: 11 } },
                ticks: { maxTicksLimit: 12, font: { size: 10 } },
            },
            y: {
                title: { display: true, text: cfg.unit, font: { size: 11 } },
                ticks: { font: { size: 10 } },
            },
        };
        if (annotations.length > 0 && typeof Chart.registry.plugins.get('annotation') !== 'undefined') {
            options.plugins.annotation = { annotations: annotations };
        }

        new Chart(canvas, {
            type: 'line',
            data: { labels: cfg.time, datasets: datasets },
            options: options,
        });
    });

    /* ----------------------------------------------------------
       Heatmap-Rendering
    ---------------------------------------------------------- */
    document.querySelectorAll('[data-heatmap]').forEach(function (container) {
        var raw = container.dataset.heatmap;
        var data;
        try { data = JSON.parse(raw); } catch (e) { return; }
        renderHeatmap(container, data);
    });

    function heatColor(val, min, max) {
        if (val == null) return '#f3f4f6';
        var t = max > min ? (val - min) / (max - min) : 0;
        t = Math.max(0, Math.min(1, t));
        // green → yellow → red
        if (t < 0.5) {
            var r = Math.round(22  + (217 - 22)  * (t * 2));
            var g = Math.round(163 + (119 - 163) * (t * 2));
            var b = Math.round(74  + (6   - 74)  * (t * 2));
            return 'rgb(' + r + ',' + g + ',' + b + ')';
        } else {
            var tt = (t - 0.5) * 2;
            var r2 = Math.round(217 + (220 - 217) * tt);
            var g2 = Math.round(119 + (38  - 119) * tt);
            var b2 = Math.round(6   + (38  - 6)   * tt);
            return 'rgb(' + r2 + ',' + g2 + ',' + b2 + ')';
        }
    }

    function renderHeatmap(container, data) {
        /* data = { time: [...], rows: [{name, values:[...]}], unit: '%' } */
        var table = document.createElement('table');
        table.className = 'heatmap-table';

        // Header row – time labels (show every Nth for readability)
        var step = Math.max(1, Math.floor(data.time.length / 40));
        var thead = table.createTHead();
        var hr = thead.insertRow();
        var th0 = document.createElement('th');
        th0.textContent = 'Element / Zeit';
        hr.appendChild(th0);
        data.time.forEach(function (t, i) {
            var th = document.createElement('th');
            th.className = 'col-header';
            th.textContent = (i % step === 0) ? (typeof t === 'number' ? t.toFixed(1) : t) : '';
            hr.appendChild(th);
        });

        // Compute global min/max
        var allVals = data.rows.flatMap(function (r) { return r.values.filter(function (v) { return v != null; }); });
        var minVal = Math.min.apply(null, allVals);
        var maxVal = Math.max.apply(null, allVals);

        // Body rows
        var tbody = table.createTBody();
        data.rows.forEach(function (row) {
            var tr = tbody.insertRow();
            var td0 = tr.insertCell();
            td0.className = 'row-label';
            td0.textContent = row.name;
            row.values.forEach(function (v) {
                var td = tr.insertCell();
                var color = heatColor(v, minVal, maxVal);
                td.style.backgroundColor = color;
                td.title = v != null ? v.toFixed(1) + ' ' + data.unit : 'n/a';
            });
        });

        container.innerHTML = '';
        container.appendChild(table);

        // Colour legend
        var leg = document.createElement('div');
        leg.style.cssText = 'display:flex;align-items:center;gap:8px;margin-top:8px;font-size:11px;color:#4b5563;';
        leg.innerHTML = '<span>' + minVal.toFixed(1) + ' ' + data.unit + '</span>'
            + '<canvas id="hm-leg-' + Math.random().toString(36).slice(2) + '" width="160" height="12" style="border-radius:4px"></canvas>'
            + '<span>' + maxVal.toFixed(1) + ' ' + data.unit + '</span>';
        container.appendChild(leg);
        var lgCanvas = leg.querySelector('canvas');
        if (lgCanvas) {
            var ctx = lgCanvas.getContext('2d');
            var grad = ctx.createLinearGradient(0, 0, 160, 0);
            grad.addColorStop(0,   heatColor(minVal, minVal, maxVal));
            grad.addColorStop(0.5, heatColor((minVal + maxVal) / 2, minVal, maxVal));
            grad.addColorStop(1,   heatColor(maxVal, minVal, maxVal));
            ctx.fillStyle = grad;
            ctx.fillRect(0, 0, 160, 12);
        }
    }

})();
