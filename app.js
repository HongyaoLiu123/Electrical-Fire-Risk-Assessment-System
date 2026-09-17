const state = {
    rows: [],
    summary: null,
    dbStartTime: '',
    dbEndTime: '',
};

const $ = (id) => document.getElementById(id);

const TYPE_LABELS = {
    temperature: '\u6e29\u5ea6',
    current: '\u7535\u6d41',
    voltage: '\u7535\u538b',
    leakage: '\u5269\u4f59\u7535\u6d41',
    energy: '\u7528\u7535\u91cf',
};

const TYPE_UNITS = {
    temperature: '\u2103',
    current: 'A',
    voltage: 'V',
    leakage: 'mA',
    energy: 'kWh',
};

const TYPE_ICONS = {
    temperature: '\ud83c\udf21\ufe0f',
    current: '\u26a1',
    voltage: '\ud83d\udd0c',
    leakage: '\u26a0\ufe0f',
    energy: '\ud83d\udd0b',
};

const SERIES_COLORS = ['#ef4444', '#3498db', '#27ae60', '#f59e0b', '#8b5cf6', '#06b6d4'];

const setText = (id, value) => {
    const el = $(id);
    if (el) el.textContent = value ?? '-';
};

const fmt = (value, suffix = '') => {
    if (value === null || value === undefined || value === '') return '-';
    return `${value}${suffix}`;
};

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function levelBadge(level) {
    const text = level || '-';
    return `<span class="badge level-${escapeHtml(text)}">${escapeHtml(text)}</span>`;
}

function countValue(counts, names) {
    for (const name of names) {
        if (counts[name] !== undefined) return counts[name];
    }
    return 0;
}

function renderSummary(summary) {
    state.summary = summary || {};
    const counts = state.summary.counts || {};

    setText('deviceCount', state.summary.deviceCount ?? 0);
    setText('matchedCount', state.summary.matchedCount ?? 0);
    setText('highCount', countValue(counts, ['\u9ad8', '\u9ad8\u98ce\u9669']));
    setText('midCount', countValue(counts, ['\u4e2d', '\u4e2d\u98ce\u9669']));
    setText('lowCount', countValue(counts, ['\u4f4e', '\u4f4e\u98ce\u9669']));
    setText('normalCount', countValue(counts, ['\u6b63\u5e38']));
}

function renderRows(rows) {
    const tbody = $('resultBody');
    if (!tbody) return;

    const keyword = $('filterInput')?.value.trim().toLowerCase() || '';
    const filtered = keyword
        ? (rows || []).filter(row => JSON.stringify(row).toLowerCase().includes(keyword))
        : (rows || []);

    if (filtered.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="12" style="text-align:center;color:#999;padding:32px;">
                    \u6682\u65e0\u6570\u636e
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = filtered.map(row => {
        const phaseType = row.phase_type || 'single';
        const phaseLabel = phaseType === 'three' ? '\u4e09\u76f8' : '\u5355\u76f8';
        const phaseClass = phaseType === 'three' ? 'phase-three' : 'phase-single';
        const devBh = escapeHtml(row.DevBH);

        return `
            <tr class="clickable-row" data-device="${devBh}" onclick="showDeviceDetail('${devBh}')">
                <td>${levelBadge(row.final_level)}</td>
                <td>${devBh}</td>
                <td>${escapeHtml(fmt(row.DevMC))}</td>
                <td>${escapeHtml(fmt(row.PartMC))}</td>
                <td><span class="phase-badge ${phaseClass}">${phaseLabel}</span></td>
                <td>${escapeHtml(fmt(row.rows))}</td>
                <td class="unit-nowrap">${escapeHtml(fmt(row.leakage_max, 'mA'))}</td>
                <td class="unit-nowrap">${escapeHtml(fmt(row.temp_max, '\u2103'))}</td>
                <td class="unit-nowrap">${escapeHtml(fmt(row.current_max, 'A'))}</td>
                <td>${escapeHtml(formatVoltage(row.voltage_min, row.voltage_max))}</td>
                <td>${escapeHtml(fmt(row.fire_hazard))}</td>
                <td>${escapeHtml(fmt(row.advice))}</td>
            </tr>
        `;
    }).join('');
}

function formatVoltage(min, max) {
    if (min === null || min === undefined || min === '') {
        return max === null || max === undefined || max === '' ? '-' : `? - ${max}V`;
    }
    if (max === null || max === undefined || max === '') return `${min}V - ?`;
    return `${min}V - ${max}V`;
}

async function checkOllama() {
    const statusEl = $('ollamaStatus');
    const modelSelect = $('model');
    if (!statusEl) return;

    try {
        const res = await fetch('/api/tags');
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || '\u4e0d\u53ef\u7528');

        const names = (data.models || []).map(model => model.name).filter(Boolean);
        statusEl.textContent = names.length ? `Ollama \u53ef\u7528\uff1a${names[0]}` : 'Ollama \u53ef\u7528';
        statusEl.className = 'status ok';

        if (modelSelect && names.length) {
            modelSelect.innerHTML = '';
            names.forEach(name => {
                const option = document.createElement('option');
                option.value = name;
                option.textContent = name;
                modelSelect.appendChild(option);
            });
            modelSelect.value = names[0];
        }
    } catch (err) {
        statusEl.textContent = `Ollama \u4e0d\u53ef\u7528\uff1a${err.message}`;
        statusEl.className = 'status bad';
    }
}

async function runMysqlQuery() {
    const notice = $('notice');
    const btn = $('dbQueryBtn');
    const start = $('dbStartTime')?.value || '';
    const end = $('dbEndTime')?.value || '';
    const keyword = $('dbKeyword')?.value.trim() || '';
    const model = $('model')?.value.trim() || 'llama3.2:latest';
    const useOllama = 'true';

    if (!start || !end) {
        if (notice) notice.textContent = '\u8bf7\u5148\u9009\u62e9\u5f00\u59cb\u65f6\u95f4\u548c\u7ed3\u675f\u65f6\u95f4';
        return;
    }

    state.dbStartTime = start;
    state.dbEndTime = end;

    const params = new URLSearchParams({
        start_time: start,
        end_time: end,
        keyword,
        model,
        use_ollama: useOllama,
    });

    try {
        if (btn) {
            btn.disabled = true;
            btn.textContent = '\u67e5\u8be2\u4e2d...';
        }
        if (notice) notice.textContent = '\u6b63\u5728\u4ece\u6570\u636e\u5e93\u67e5\u8be2\u5e76\u5206\u6790...';

        const res = await fetch(`/api/mysql/analyze?${params.toString()}`);
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || '\u6570\u636e\u5e93\u67e5\u8be2\u5931\u8d25');

        state.rows = data.rows || [];
        renderSummary(data.summary);
        renderRows(state.rows);

        if (notice) {
            notice.textContent = `\u67e5\u8be2\u5b8c\u6210\uff0c\u5171 ${state.rows.length} \u6761\u8bbe\u5907\u7ed3\u679c\u3002\u70b9\u51fb\u8bbe\u5907\u884c\u53ef\u67e5\u770b\u8be6\u60c5\u3002`;
        }
    } catch (err) {
        if (notice) notice.textContent = `\u6570\u636e\u5e93\u67e5\u8be2\u5931\u8d25\uff1a${err.message}`;
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = '\u4ece\u6570\u636e\u5e93\u67e5\u8be2';
        }
    }
}

function showDeviceDetail(devBh) {
    const oldOverlay = $('modal-overlay');
    if (oldOverlay) oldOverlay.remove();

    const overlay = document.createElement('div');
    overlay.id = 'modal-overlay';
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <h2 id="modalTitle">\u8bbe\u5907\u6570\u636e\u8be6\u60c5</h2>
                <button class="modal-close" onclick="closeModal()">\u00d7</button>
            </div>
            <div class="modal-body" id="modalBody">
                <div class="modal-loading">\u6b63\u5728\u52a0\u8f7d\u8bbe\u5907\u8be6\u60c5...</div>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);
    loadDeviceChart(devBh);
}

function closeModal() {
    document.querySelectorAll('.data-point-popup').forEach(el => el.remove());
    const overlay = $('modal-overlay');
    if (overlay) overlay.remove();
}

async function loadDeviceChart(devBh) {
    const modalBody = $('modalBody');
    const modalTitle = $('modalTitle');

    try {
        const params = new URLSearchParams({
            start_time: state.dbStartTime,
            end_time: state.dbEndTime,
        });
        const res = await fetch(`/api/mysql/chart/${encodeURIComponent(devBh)}?${params.toString()}`);
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || '\u52a0\u8f7d\u5931\u8d25');

        const info = data.data;
        const rowInfo = state.rows.find(row => String(row.DevBH) === String(devBh)) || {};
        const timeline = info.timeline || [];

        if (modalTitle) modalTitle.textContent = `${info.dev_name || info.dev_bh} - \u8bbe\u5907\u6570\u636e\u8be6\u60c5`;
        if (!modalBody) return;

        modalBody.innerHTML = `
            ${buildDeviceInfoHtml(info)}
            ${buildAiAdviceHtml(rowInfo)}
            ${buildStatsSummaryHtml(timeline)}
            ${buildAllChartsHtml(timeline)}
        `;

        renderAllCharts(timeline);
    } catch (err) {
        if (modalBody) {
            modalBody.innerHTML = `<div class="modal-error">\u52a0\u8f7d\u5931\u8d25\uff1a${escapeHtml(err.message)}</div>`;
        }
    }
}

function buildDeviceInfoHtml(info) {
    const phaseLabel = info.phase_type === 'three' ? '\u4e09\u76f8\u7535' : '\u5355\u76f8\u7535';
    return `
        <div class="device-info-grid">
            ${infoItem('\u8bbe\u5907\u7f16\u53f7', info.dev_bh)}
            ${infoItem('\u8bbe\u5907\u540d\u79f0', info.dev_name || '-')}
            ${infoItem('\u533a\u57df', info.part_mc || '-')}
            ${infoItem('\u4f9b\u7535\u7c7b\u578b', `<span class="phase-badge ${info.phase_type === 'three' ? 'phase-three' : 'phase-single'}">${phaseLabel}</span>`, true)}
            ${infoItem('\u6570\u636e\u6761\u6570', info.data_count)}
            ${infoItem('\u603b\u7528\u7535\u91cf', fmt(info.total_energy, ' kWh'))}
        </div>
    `;
}

function infoItem(label, value, raw = false) {
    return `
        <div class="info-item">
            <span class="info-label">${escapeHtml(label)}</span>
            <span class="info-value">${raw ? value : escapeHtml(fmt(value))}</span>
        </div>
    `;
}

function getDeviceLocation(rowInfo) {
    return rowInfo.Address || rowInfo.PartMC || rowInfo.DevMC || rowInfo.DevBH || '-';
}

function buildDangerSourceItems(rowInfo) {
    const location = getDeviceLocation(rowInfo);
    const items = [];

    if (rowInfo.temp_max !== null && rowInfo.temp_max !== undefined) {
        items.push({
            title: '温度风险',
            detail: `最高温度 ${formatNumber(rowInfo.temp_max)}℃，时间：${fmt(rowInfo.temp_max_time)}，位置：${fmt(location)}`,
            level: Number(rowInfo.temp_max) >= 60 ? 'danger' : Number(rowInfo.temp_max) >= 45 ? 'watch' : 'normal',
        });
    }
    if (rowInfo.leakage_max !== null && rowInfo.leakage_max !== undefined) {
        items.push({
            title: '剩余电流风险',
            detail: `最大剩余电流 ${formatNumber(rowInfo.leakage_max)}mA，时间：${fmt(rowInfo.leakage_max_time)}，位置：${fmt(location)}`,
            level: Number(rowInfo.leakage_max) >= 300 ? 'danger' : Number(rowInfo.leakage_max) >= 200 ? 'watch' : 'normal',
        });
    }
    if (rowInfo.current_max !== null && rowInfo.current_max !== undefined) {
        items.push({
            title: '电流风险',
            detail: `最大电流 ${formatNumber(rowInfo.current_max)}A，时间：${fmt(rowInfo.current_max_time)}，位置：${fmt(location)}`,
            level: 'watch',
        });
    }
    if (rowInfo.voltage_min !== null && rowInfo.voltage_min !== undefined && rowInfo.voltage_max !== null && rowInfo.voltage_max !== undefined) {
        items.push({
            title: '电压风险',
            detail: `电压范围 ${formatNumber(rowInfo.voltage_min)}V - ${formatNumber(rowInfo.voltage_max)}V，低压时间：${fmt(rowInfo.voltage_min_time)}，高压时间：${fmt(rowInfo.voltage_max_time)}，位置：${fmt(location)}`,
            level: Number(rowInfo.voltage_min) < 187 || Number(rowInfo.voltage_max) > 253 ? 'watch' : 'normal',
        });
    }

    (rowInfo.extreme_points || []).slice(0, 4).forEach(point => {
        items.push({
            title: '极端数据点',
            detail: `${fmt(point.name)} ${formatNumber(point.value)}${fmt(point.unit)}，时间：${fmt(point.time)}，位置：${fmt(location)}，偏离中位数：${formatNumber(point.delta_from_median)}${fmt(point.unit)}`,
            level: 'danger',
        });
    });

    (rowInfo.trend_summary || [])
        .filter(item => item.concern === 'danger' || item.concern === 'watch')
        .slice(0, 4)
        .forEach(item => {
            const directionMap = {
                rising: '持续上升',
                falling: '持续下降',
                fluctuating: '波动明显',
                stable: '整体平稳',
            };
            items.push({
                title: item.concern === 'danger' ? '危险趋势' : '趋势隐患',
                detail: `${fmt(item.name)}呈${directionMap[item.direction] || fmt(item.direction)}，从 ${formatNumber(item.start_value)}${fmt(item.unit)} 变化到 ${formatNumber(item.end_value)}${fmt(item.unit)}，最大跳变 ${formatNumber(item.max_step)}${fmt(item.unit)}，时间：${fmt(item.max_step_time)}，位置：${fmt(location)}`,
                level: item.concern,
            });
        });

    return items;
}

function buildDangerSourceHtml(rowInfo) {
    const items = buildDangerSourceItems(rowInfo);
    if (!items.length) {
        return `
            <div class="ai-evidence-card">
                <h4>危险源与趋势依据</h4>
                <p>当前未发现明显越限点，但仍需结合趋势变化、现场负载和环境条件持续复核。</p>
            </div>
        `;
    }

    return `
        <div class="ai-evidence-card">
            <h4>危险源与趋势依据</h4>
            <div class="evidence-list">
                ${items.map(item => `
                    <div class="evidence-item evidence-${item.level}">
                        <strong>${escapeHtml(item.title)}</strong>
                        <span>${escapeHtml(item.detail)}</span>
                    </div>
                `).join('')}
            </div>
        </div>
    `;
}

function buildAiAdviceHtml(rowInfo) {
    if (!rowInfo || Object.keys(rowInfo).length === 0) return '';

    const source = rowInfo.analysis_source || (rowInfo.ollama_model_level ? 'ollama' : 'ollama_failed');
    const sourceText = source === 'ollama'
        ? '来源：Ollama AI'
        : 'AI 暂不可用，显示规则证据与兜底建议';
    const sourceClass = source === 'ollama' ? 'source-ai' : 'source-failed';
    const sourceNote = rowInfo.analysis_error
        ? `<p class="ai-source-error">${escapeHtml(rowInfo.analysis_error)}</p>`
        : '';

    return `
        <div class="chart-section ai-analysis-section">
            <div class="ai-section-title">
                <h3>🤖 AI 研判与巡检建议</h3>
                <span class="ai-source-badge ${sourceClass}">${escapeHtml(sourceText)}</span>
            </div>
            <div class="ai-analysis-grid">
                <div class="ai-level-card">
                    <h4>最终等级</h4>
                    <div class="ai-level-badge">${escapeHtml(rowInfo.final_level || '-')}</div>
                </div>
                <div class="ai-result-card">
                    <h4>AI 研判结果</h4>
                    <p>${escapeHtml(rowInfo.fire_hazard || rowInfo.reason || '-')}</p>
                </div>
            </div>
            ${buildDangerSourceHtml(rowInfo)}
            <div class="ai-advice-card">
                <h4>专业巡检建议</h4>
                <p>${escapeHtml(rowInfo.advice || '-')}</p>
                ${sourceNote}
            </div>
        </div>
    `;
}

function buildStatsSummaryHtml(timeline) {
    const groups = groupTimeline(timeline);
    const ordered = ['temperature', 'current', 'voltage', 'leakage', 'energy'];
    const html = ordered
        .filter(type => groups[type]?.length)
        .map(type => buildTypeStatsSection(type, groups[type]))
        .join('');

    if (!html) return '';
    return `<div class="chart-section"><h3>\ud83d\udcc8 \u7edf\u8ba1\u6458\u8981</h3>${html}</div>`;
}

function buildTypeStatsSection(type, items) {
    const cards = items.map(item => `
        <div class="summary-stat-card">
            <h4>${escapeHtml(item.name)}</h4>
            <p>
                ${item.total !== undefined ? `\u603b\u7528\u7535\u91cf: ${escapeHtml(fmt(item.total, TYPE_UNITS[type] || ''))}` : `\u6700\u5927: ${escapeHtml(fmt(item.max, TYPE_UNITS[type] || ''))}`}
                ${item.min !== undefined && item.total === undefined ? `&nbsp;&nbsp;\u6700\u5c0f: ${escapeHtml(fmt(item.min, TYPE_UNITS[type] || ''))}` : ''}
            </p>
            <p>
                ${item.avg !== undefined ? `\u5e73\u5747: ${escapeHtml(fmt(item.avg, TYPE_UNITS[type] || ''))}` : ''}
                &nbsp;&nbsp;\u6837\u672c: ${escapeHtml(fmt(item.count))}
            </p>
        </div>
    `).join('');

    return `
        <div class="summary-type-section">
            <h4>${TYPE_ICONS[type] || ''} ${escapeHtml(TYPE_LABELS[type] || type)}</h4>
            <div class="summary-stat-grid">${cards}</div>
        </div>
    `;
}

function buildAllChartsHtml(timeline) {
    const groups = groupTimeline(timeline);
    const ordered = ['temperature', 'current', 'voltage', 'leakage', 'energy'];
    const sections = ordered
        .filter(type => groups[type]?.length)
        .map(type => `
            <div class="chart-section">
                <div class="chart-header">
                    <h3>${TYPE_ICONS[type] || ''} ${escapeHtml(TYPE_LABELS[type] || type)}\u53d8\u5316</h3>
                    ${buildThresholdLegend(type)}
                </div>
                <div id="chart-${type}" class="echart-box"></div>
            </div>
        `)
        .join('');

    if (!sections) {
        return `<div class="chart-section"><h3>\ud83d\udcc9 \u53d8\u5316\u8d8b\u52bf</h3><div class="modal-error">\u8be5\u8bbe\u5907\u6ca1\u6709\u53ef\u7ed8\u5236\u7684\u65f6\u5e8f\u6570\u636e</div></div>`;
    }

    return `
        <div class="chart-section">
            <h3>\ud83d\udcc9 \u53d8\u5316\u8d8b\u52bf <small>\uff08\u70b9\u51fb\u56fe\u8868\u5706\u70b9\u67e5\u770b\u5177\u4f53\u6570\u636e\uff09</small></h3>
        </div>
        ${sections}
    `;
}

function buildThresholdLegend(type) {
    if (type === 'temperature') {
        return `<div class="chart-thresholds"><span class="warn">\u8b66\u6212\u7ebf 45\u2103</span><span class="danger">\u5371\u9669\u7ebf 60\u2103</span></div>`;
    }
    if (type === 'leakage') {
        return `<div class="chart-thresholds"><span class="danger">\u706b\u707e\u98ce\u9669 300mA</span></div>`;
    }

    if (type === 'voltage') {
        return `<div class="chart-thresholds"><span class="warn">\u6b63\u5e38\u8303\u56f4 187V-253V</span></div>`;
    }
    return '';
}

function renderAllCharts(timeline) {
    const groups = groupTimeline(timeline);
    Object.keys(groups).forEach(type => renderTypeChart(type, groups[type]));
}

function groupTimeline(timeline) {
    return (timeline || []).reduce((acc, item) => {
        if (!item.type) return acc;
        if (!acc[item.type]) acc[item.type] = [];
        acc[item.type].push(item);
        return acc;
    }, {});
}

function renderTypeChart(type, items) {
    const chartEl = $(`chart-${type}`);
    if (!chartEl || !window.echarts || !items?.length) return;

    const chart = echarts.init(chartEl);
    const labels = getBestLabels(items);
    const unit = TYPE_UNITS[type] || '';
    const chartItems = type === 'energy' ? items.map(toEnergyDeltaSeries) : items;
    const chartLabels = type === 'energy'
        ? (chartItems.find(item => item.time_labels && item.time_labels.length)?.time_labels || [])
        : labels;
    const series = chartItems.map((item, index) => ({
        name: item.name,
        type: type === 'energy' ? 'bar' : 'line',
        smooth: type !== 'energy',
        showSymbol: true,
        symbolSize: 6,
        lineStyle: { width: 3 },
        itemStyle: { color: SERIES_COLORS[index % SERIES_COLORS.length] },
        data: item.data || [],
    }));

    const option = {
        tooltip: {
            trigger: 'axis',
            formatter(params) {
                const title = params?.[0]?.axisValueLabel || '';
                const lines = params.map(p => `${p.marker}${escapeHtml(p.seriesName)}: ${p.value}${unit}`).join('<br/>');
                return `${escapeHtml(title)}<br/>${lines}`;
            },
        },
        legend: { type: 'scroll', top: 0 },
        grid: { top: 64, left: 70, right: 86, bottom: 64 },
        xAxis: {
            type: 'category',
            name: '\u65f6\u95f4',
            data: chartLabels,
            axisLabel: { rotate: 45, hideOverlap: true },
        },
        yAxis: {
            type: 'value',
            name: `${TYPE_LABELS[type] || ''}${unit ? ` (${unit})` : ''}`,
            scale: true,
        },
        series,
    };

    const markLines = getMarkLines(type);
    if (markLines.length) {
        option.series.push({
            name: '\u9608\u503c',
            type: 'line',
            data: [],
            markLine: {
                symbol: 'none',
                data: markLines,
                label: { formatter: '{b}' },
            },
        });
    }

    chart.setOption(option, true);

    chart.off('legendselectchanged');
    chart.on('legendselectchanged', params => {
        if (!params.name || params.name === '\u9608\u503c') return;

        const item = chartItems.find(seriesItem => seriesItem.name === params.name);
        if (!item) return;

        const selected = {};
        chartItems.forEach(seriesItem => {
            selected[seriesItem.name] = true;
        });

        chart.setOption({ legend: { selected } });
        showSeriesAnalysisPopup(type, item, unit);
    });

    chart.off('click');
    chart.on('click', params => {
        if (params.componentType !== 'series' || params.seriesName === '\u9608\u503c') return;
        const item = chartItems.find(seriesItem => seriesItem.name === params.seriesName);
        if (!item) return;
        showDataPointPopup({
            seriesName: item.name,
            type: item.type,
            time: item.time_labels?.[params.dataIndex] ?? chartLabels[params.dataIndex],
            value: params.value,
            unit,
            index: params.dataIndex + 1,
        });
    });
}


function toEnergyDeltaSeries(item) {
    const rawValues = (item.data || []).map(value => Number(value));
    const rawLabels = item.time_labels || [];
    const deltaValues = [];
    const deltaLabels = [];

    for (let index = 1; index < rawValues.length; index += 1) {
        const current = rawValues[index];
        const previous = rawValues[index - 1];

        if (!Number.isFinite(current) || !Number.isFinite(previous)) {
            continue;
        }

        const delta = current - previous;
        if (delta < 0) {
            continue;
        }

        deltaValues.push(Number(delta.toFixed(4)));
        const previousLabel = formatTimeLabel(rawLabels[index - 1] ?? String(index));
        const currentLabel = formatTimeLabel(rawLabels[index] ?? String(index + 1));
        deltaLabels.push(`${previousLabel}~${currentLabel}`);
    }

    return {
        ...item,
        data: deltaValues,
        time_labels: deltaLabels,
        name: item.name || '用电量',
        original_data: item.data || [],
    };
}

function getMarkLines(type) {
    if (type === 'temperature') {
        return [
            { name: '\u8b66\u6212\u7ebf 45\u2103', yAxis: 45, lineStyle: { color: '#f59e0b', type: 'dashed', width: 2 } },
            { name: '\u5371\u9669\u7ebf 60\u2103', yAxis: 60, lineStyle: { color: '#ef4444', type: 'dashed', width: 2 } },
        ];
    }
    if (type === 'leakage') {
        return [
            { name: '\u706b\u707e\u98ce\u9669 300mA', yAxis: 300, lineStyle: { color: '#ef4444', type: 'dashed', width: 2 } },
        ];
    }
    if (type === 'voltage') {
        return [
            { name: '\u4e0b\u9650 187V', yAxis: 187, lineStyle: { color: '#f59e0b', type: 'dashed', width: 2 } },
            { name: '\u4e0a\u9650 253V', yAxis: 253, lineStyle: { color: '#f59e0b', type: 'dashed', width: 2 } },
        ];
    }
    return [];
}

function getBestLabels(seriesList) {
    const first = seriesList.find(item => item.time_labels && item.time_labels.length);
    if (first) return first.time_labels.map(formatTimeLabel);
    const maxLength = Math.max(0, ...seriesList.map(item => (item.data || []).length));
    return Array.from({ length: maxLength }, (_, index) => String(index + 1));
}

function formatTimeLabel(value) {
    const text = String(value ?? '');
    const match = text.match(/(\d{2}):(\d{2})(?::\d{2})?/);
    return match ? `${match[1]}:${match[2]}` : text;
}


function showSeriesAnalysisPopup(type, seriesItem, unit = '') {
    document.querySelectorAll('.current-analysis-popup').forEach(el => el.remove());

    const values = (seriesItem.data || [])
        .map(value => Number(value))
        .filter(value => Number.isFinite(value));

    if (!values.length) return;

    const labels = (seriesItem.time_labels && seriesItem.time_labels.length)
        ? (type === 'energy' ? seriesItem.time_labels : seriesItem.time_labels.map(formatTimeLabel))
        : values.map((_, index) => String(index + 1));

    const stats = getSeriesStats(values, labels, type, unit);
    const chartId = `single-analysis-chart-${Date.now()}`;
    const analysisId = `series-ai-analysis-${Date.now()}`;
    const title = `${seriesItem.name}数据分析`;
    const subtitle = getAnalysisSubtitle(type, seriesItem.name);

    const popup = document.createElement('div');
    popup.className = 'current-analysis-popup';
    popup.innerHTML = `
        <div class="current-analysis-content">
            <div class="current-analysis-header">
                <div>
                    <h2>${escapeHtml(title)}</h2>
                    <p>${escapeHtml(subtitle)}</p>
                </div>
                <button type="button" onclick="this.closest('.current-analysis-popup').remove()">×</button>
            </div>

            <div class="current-analysis-body">
                <div id="${chartId}" class="single-current-chart"></div>

                <div class="analysis-panels">
                    <div class="analysis-card">
                        <h3>数据统计概览</h3>
                        <div class="stat-grid">
                            <div class="stat-row stat-row-top">
                                <div>
                                    <small>有效记录数</small>
                                    <span>${stats.count}</span>
                                </div>
                                <div class="time-range">
                                    <small>时间范围</small>
                                    <span>${escapeHtml(stats.startTime)} ~ ${escapeHtml(stats.endTime)}</span>
                                </div>
                                <div>
                                    <small>${escapeHtml(stats.ratioLabel)}</small>
                                    <span>${stats.overRatio}%</span>
                                </div>
                            </div>

                            <div class="stat-row stat-row-bottom">
                                <div>
                                    <small>最小值</small>
                                    <span>${formatNumber(stats.min)}${escapeHtml(unit)}</span>
                                </div>
                                <div>
                                    <small>最大值</small>
                                    <span>${formatNumber(stats.max)}${escapeHtml(unit)}</span>
                                </div>
                                <div>
                                    <small>平均值</small>
                                    <span>${formatNumber(stats.avg)}${escapeHtml(unit)}</span>
                                </div>
                                <div>
                                    <small>${escapeHtml(stats.overLabel)}</small>
                                    <span>${stats.overCount}</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="analysis-card">
                        <div class="analysis-card-head">
                            <h3>分析结论</h3>
                            <div class="analysis-tabs" role="tablist" aria-label="分析结论切换">
                                <button type="button" class="analysis-tab-btn active" data-target="${analysisId}" data-mode="summary">数据总结</button>
                                <button type="button" class="analysis-tab-btn" data-target="${analysisId}" data-mode="ai">AI 研判</button>
                            </div>
                        </div>
                        <div id="${analysisId}" class="series-ai-analysis analysis-switcher">
                            <div class="analysis-panel active" data-panel="summary">
                                <ol>
                                    ${buildAnalysisConclusion(type, seriesItem.name, stats, unit)}
                                </ol>
                                <p class="ai-source-note">以上为规则和曲线统计生成的数据总结，可切换到 AI 研判查看模型分析。</p>
                            </div>
                            <div class="analysis-panel" data-panel="ai">
                                <div class="ai-loading">AI 正在结合曲线统计生成分析结论...</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;

    document.body.appendChild(popup);
    popup.addEventListener('click', event => {
        if (event.target === popup) popup.remove();
    });
    popup.querySelectorAll('.analysis-tab-btn').forEach(button => {
        button.addEventListener('click', () => {
            switchSeriesAnalysisTab(button.dataset.target, button.dataset.mode);
        });
    });

    renderSingleAnalysisChart(chartId, type, seriesItem.name, values, labels, unit);
    requestSeriesAiAnalysis(analysisId, type, seriesItem.name, stats, unit);
}




function switchSeriesAnalysisTab(containerId, mode) {
    const container = $(containerId);
    if (!container) return;

    const card = container.closest('.analysis-card');
    card?.querySelectorAll('.analysis-tab-btn').forEach(button => {
        button.classList.toggle('active', button.dataset.mode === mode);
    });
    container.querySelectorAll('.analysis-panel').forEach(panel => {
        panel.classList.toggle('active', panel.dataset.panel === mode);
    });
}

function analyzeSeriesTrend(values, labels, type, unit = '') {
    if (!values || values.length < 3) {
        return {
            direction: 'unknown',
            description: '有效数据不足，暂无法判断趋势。',
        };
    }

    const first = values[0];
    const last = values[values.length - 1];
    const change = last - first;
    const changeRatio = first ? (change / Math.abs(first)) * 100 : 0;
    const avg = values.reduce((sum, value) => sum + value, 0) / values.length;
    const variance = values.reduce((sum, value) => sum + Math.pow(value - avg, 2), 0) / values.length;
    const volatility = avg ? (Math.sqrt(variance) / Math.abs(avg)) * 100 : 0;
    const diffs = values.slice(1).map((value, index) => ({
        value: value - values[index],
        abs: Math.abs(value - values[index]),
        time: labels[index + 1] || '-',
    }));
    const maxStep = diffs.reduce((best, item) => item.abs > best.abs ? item : best, { value: 0, abs: 0, time: '-' });

    let direction = 'stable';
    if (Math.abs(changeRatio) >= 8 || Math.abs(change) >= Math.max(1, Math.abs(avg) * 0.08)) {
        direction = change > 0 ? 'rising' : 'falling';
    } else if (volatility >= 6 || maxStep.abs >= Math.max(1, Math.abs(avg) * 0.12)) {
        direction = 'fluctuating';
    }

    const directionText = {
        rising: '整体上升',
        falling: '整体下降',
        fluctuating: '波动明显',
        stable: '整体平稳',
        unknown: '趋势不足',
    }[direction] || direction;

    let concern = 'normal';
    if (type === 'temperature' && (last >= 45 && direction === 'rising')) concern = 'watch';
    if (type === 'temperature' && values.some(value => value >= 60)) concern = 'danger';
    if (type === 'leakage' && (last >= 200 && direction === 'rising')) concern = 'watch';
    if (type === 'leakage' && values.some(value => value >= 300)) concern = 'danger';
    if (type === 'current' && (direction === 'rising' || maxStep.abs >= Math.max(5, Math.abs(avg) * 0.2))) concern = 'watch';
    if (type === 'voltage' && (values.some(value => value < 187 || value > 253) || volatility >= 4)) concern = 'watch';

    return {
        direction,
        directionText,
        concern,
        startTime: labels[0] || '-',
        endTime: labels[labels.length - 1] || '-',
        startValue: Number(first.toFixed(3)),
        endValue: Number(last.toFixed(3)),
        change: Number(change.toFixed(3)),
        changeRatio: Number(changeRatio.toFixed(2)),
        volatility: Number(volatility.toFixed(2)),
        maxStep: Number(maxStep.abs.toFixed(3)),
        maxStepTime: maxStep.time,
        unit,
        description: `${directionText}，从 ${formatNumber(first)}${unit} 变化到 ${formatNumber(last)}${unit}，最大相邻变化 ${formatNumber(maxStep.abs)}${unit}。`,
    };
}

function detectSeriesExtremePoints(values, labels, type, unit = '') {
    if (!values || values.length < 5) return [];

    const sorted = [...values].sort((a, b) => a - b);
    const median = sorted[Math.floor(sorted.length / 2)];
    const deviations = values.map(value => Math.abs(value - median)).sort((a, b) => a - b);
    const mad = deviations[Math.floor(deviations.length / 2)];
    const avg = values.reduce((sum, value) => sum + value, 0) / values.length;
    const variance = values.reduce((sum, value) => sum + Math.pow(value - avg, 2), 0) / values.length;
    const std = Math.sqrt(variance);
    const scale = mad > 0 ? mad * 1.4826 : std;
    if (!scale) return [];

    const minDeltaByType = {
        temperature: 8,
        current: 5,
        voltage: 12,
        leakage: 60,
        energy: 0.2,
    };
    const minDelta = minDeltaByType[type] ?? 5;

    return values
        .map((value, index) => {
            const delta = Math.abs(value - median);
            const severity = delta / scale;
            const prev = index > 0 ? values[index - 1] : null;
            const next = index < values.length - 1 ? values[index + 1] : null;
            const neighbors = [prev, next].filter(v => Number.isFinite(v));
            const neighborAvg = neighbors.length
                ? neighbors.reduce((sum, v) => sum + v, 0) / neighbors.length
                : null;
            const neighborDelta = Number.isFinite(neighborAvg) ? Math.abs(value - neighborAvg) : null;

            return {
                index: index + 1,
                time: labels[index] || '-',
                value,
                unit,
                median,
                delta_from_median: delta,
                neighbor_delta: neighborDelta,
                severity,
                reason: '该点相对同类数据中位数偏离明显，疑似极端点。',
            };
        })
        .filter(point => point.severity >= 6 && point.delta_from_median >= minDelta)
        .sort((a, b) => b.severity - a.severity)
        .slice(0, 6)
        .map(point => ({
            ...point,
            value: Number(point.value.toFixed(3)),
            median: Number(point.median.toFixed(3)),
            delta_from_median: Number(point.delta_from_median.toFixed(3)),
            neighbor_delta: Number.isFinite(point.neighbor_delta) ? Number(point.neighbor_delta.toFixed(3)) : null,
            severity: Number(point.severity.toFixed(2)),
        }));
}

function getSeriesStats(values, labels, type, unit = '') {
    const count = values.length;
    const max = Math.max(...values);
    const min = Math.min(...values);
    const avg = values.reduce((sum, value) => sum + value, 0) / count;
    const maxIndex = values.indexOf(max);
    const minIndex = values.indexOf(min);
    const threshold = getAnalysisThreshold(type);
    const overCount = threshold
        ? values.filter(value => threshold.test(value)).length
        : 0;
    const extremePoints = detectSeriesExtremePoints(values, labels, type, unit);
    const trendSummary = analyzeSeriesTrend(values, labels, type, unit);

    return {
        count,
        max,
        min,
        avg,
        maxTime: labels[maxIndex] || '-',
        minTime: labels[minIndex] || '-',
        startTime: labels[0] || '-',
        endTime: labels[labels.length - 1] || '-',
        overCount,
        overRatio: count ? ((overCount / count) * 100).toFixed(1) : '0.0',
        overLabel: threshold?.countLabel || '异常次数',
        ratioLabel: threshold?.ratioLabel || '异常占比',
        extremePoints,
        extremeCount: extremePoints.length,
        trendSummary,
    };
}

function getAnalysisThreshold(type) {
    const thresholds = {
        leakage: {
            yAxis: 300,
            label: '火灾风险300mA',
            countLabel: '≥300mA次数',
            ratioLabel: '高位占比',
            test: value => value >= 300,
        },
        temperature: {
            yAxis: 60,
            label: '危险线60℃',
            countLabel: '≥60℃次数',
            ratioLabel: '危险占比',
            test: value => value >= 60,
        },
        current: {
            yAxis: 30,
            label: '高电流30A',
            countLabel: '≥30A次数',
            ratioLabel: '高位占比',
            test: value => value >= 30,
        },
        voltage: {
            label: '超出187V-253V',
            countLabel: '越限次数',
            ratioLabel: '越限占比',
            test: value => value < 187 || value > 253,
        },
    };

    return thresholds[type] || null;
}

function getAnalysisSubtitle(type, name) {
    if (type === 'temperature') return `${name}曲线 · 温度阈值：警戒45℃ / 危险60℃`;
    if (type === 'voltage') return `${name}曲线 · 正常参考范围：187V ~ 253V`;
    if (type === 'leakage') return `${name}曲线 · 火灾风险阈值：300mA`;
    if (type === 'current') return `${name}曲线 · 电流运行变化`;
    if (type === 'energy') return `${name}柱状图 · 相邻刻度差值，表示每个时间段用电量`;
    return `${name}曲线 · 单参数分析`;
}

function buildAnalysisConclusion(type, name, stats, unit) {
    return getRuleAnalysisLines(type, name, stats, unit)
        .map(line => `<li>${escapeHtml(line)}</li>`)
        .join('');
}

function getRuleAnalysisLines(type, name, stats, unit) {
    const lines = [
        `${name}最大值为 ${formatNumber(stats.max)}${unit}，出现在 ${stats.maxTime}。`,
        `平均值为 ${formatNumber(stats.avg)}${unit}，最小值为 ${formatNumber(stats.min)}${unit}。`,
    ];

    if (stats.trendSummary) {
        lines.push(`趋势判断：${stats.trendSummary.description}`);
        if (stats.trendSummary.concern === 'danger') {
            lines.push('该趋势已伴随危险阈值或高风险点，应优先复核接线端子、负载变化、散热条件和采集记录。');
        } else if (stats.trendSummary.concern === 'watch') {
            lines.push('该趋势需要关注，建议对比同一回路负载变化和环境变化，必要时缩短巡检周期。');
        }
    }

    if (stats.extremeCount > 0 && stats.extremePoints?.length) {
        const firstExtreme = stats.extremePoints[0];
        lines.push(`检测到 ${stats.extremeCount} 个疑似极端数据点，最明显点为 ${formatNumber(firstExtreme.value)}${unit}，出现在 ${firstExtreme.time}，建议结合原始采集记录和现场负载变化复核。`);
    }

    if (type === 'voltage') {
        lines.push(`超出187V~253V正常范围共 ${stats.overCount} 次，占比 ${stats.overRatio}%。`);
        lines.push(stats.overCount > 0
            ? '存在电压越限现象，建议检查供电质量、线路连接和负载波动情况。'
            : '未发现明显电压越限，电压运行状态较稳定。');
    } else if (type === 'temperature') {
        lines.push(`≥60℃危险温度共 ${stats.overCount} 次，占比 ${stats.overRatio}%。`);
        lines.push(stats.overCount > 0
            ? '存在温度异常升高，建议重点检查接线端子、负载发热和散热环境。'
            : '未发现明显危险温度点，建议继续关注温度趋势变化。');
    } else if (type === 'leakage') {
        lines.push(`≥300mA高位运行共 ${stats.overCount} 次，占比 ${stats.overRatio}%。`);
        lines.push(stats.overCount > 0
            ? '存在火灾风险剩余电流，建议结合负载容量和回路情况进一步核查。'
            : '未发现明显高剩余电流运行区间。');
    } else if (type === 'current') {
        lines.push(`≥30A高电流运行共 ${stats.overCount} 次，占比 ${stats.overRatio}%。`);
        lines.push(stats.overCount > 0
            ? '存在高电流运行区间，建议核对负载容量和回路运行状态。'
            : '未发现明显高电流运行区间。');
    } else if (type === 'energy') {
        lines.push(`本图按相邻两个刻度的累计电量差值计算，共 ${stats.count} 个用电区间。`);
        lines.push(`峰值区间用电量为 ${formatNumber(stats.max)}${unit}，出现在 ${stats.maxTime}。`);
    } else {
        lines.push(`本曲线共有 ${stats.count} 条有效记录，可结合上方趋势继续判断运行稳定性。`);
    }

    return lines;
}

async function requestSeriesAiAnalysis(containerId, type, name, stats, unit) {
    const container = $(containerId);
    if (!container) return;

    const aiPanel = container.querySelector('[data-panel="ai"]');
    if (!aiPanel) return;

    const model = $('model')?.value.trim() || 'llama3.2:latest';
    aiPanel.innerHTML = `<div class="ai-loading">AI 正在结合曲线统计生成分析结论...</div>`;

    try {
        const res = await fetch('/api/ai/series-analysis', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model,
                type,
                type_label: TYPE_LABELS[type] || type,
                name,
                unit,
                stats,
                rule_lines: getRuleAnalysisLines(type, name, stats, unit),
            }),
        });

        const data = await res.json();
        if (!data.ok) throw new Error(data.error || 'AI 分析失败');

        const analysis = data.analysis || {};
        const lines = Array.isArray(analysis.conclusion_lines)
            ? analysis.conclusion_lines
            : [];
        const summary = analysis.summary || '';
        const advice = analysis.advice || '';

        aiPanel.innerHTML = `
            ${summary ? `<p class="ai-summary">${escapeHtml(summary)}</p>` : ''}
            <ol>
                ${lines.map(line => `<li>${escapeHtml(line)}</li>`).join('')}
            </ol>
            ${advice ? `<div class="ai-advice"><strong>巡检建议：</strong>${escapeHtml(advice)}</div>` : ''}
            <p class="ai-source-note">以上内容由 Ollama 根据该曲线统计摘要生成，数据总结可通过上方按钮切回查看。</p>
        `;

        const aiButton = container.closest('.analysis-card')?.querySelector('.analysis-tab-btn[data-mode="ai"]');
        if (aiButton) aiButton.textContent = 'AI 研判已生成';
    } catch (err) {
        aiPanel.innerHTML = `
            <div class="ai-advice"><strong>AI 分析失败：</strong>${escapeHtml(err.message)}</div>
            <p class="ai-source-note">当前仍可切回“数据总结”查看规则和曲线统计结论。</p>
        `;
    }
}


function getSingleChartYAxis(type, values, threshold) {
    const finiteValues = (values || []).map(Number).filter(Number.isFinite);
    if (!finiteValues.length) {
        return {
            scale: true,
        };
    }

    const dataMin = Math.min(...finiteValues);
    const dataMax = Math.max(...finiteValues);
    const dataSpan = dataMax - dataMin;

    if (type === 'temperature') {
        const shouldShowThreshold = threshold?.yAxis !== undefined && dataMax >= threshold.yAxis * 0.75;
        const baseMin = dataMin;
        const baseMax = shouldShowThreshold ? Math.max(dataMax, threshold.yAxis) : dataMax;
        const span = Math.max(baseMax - baseMin, 0.1);
        const padding = Math.max(span * 0.28, shouldShowThreshold ? 2 : 0.35);
        return {
            scale: true,
            min: Math.floor((baseMin - padding) * 10) / 10,
            max: Math.ceil((baseMax + padding) * 10) / 10,
            splitNumber: 5,
        };
    }

    if (type === 'energy') {
        const padding = Math.max(dataSpan * 0.2, 0.1);
        return {
            scale: true,
            min: Math.max(0, Math.floor((dataMin - padding) * 10) / 10),
            max: Math.ceil((dataMax + padding) * 10) / 10,
            splitNumber: 5,
        };
    }

    if (type === 'leakage') {
        const upper = threshold?.yAxis !== undefined && dataMax >= threshold.yAxis * 0.75
            ? Math.max(dataMax, threshold.yAxis)
            : dataMax;
        const span = Math.max(upper - dataMin, 1);
        const padding = Math.max(span * 0.2, 5);
        return {
            scale: true,
            min: Math.max(0, Math.floor(dataMin - padding)),
            max: Math.ceil(upper + padding),
            splitNumber: 5,
        };
    }

    const span = Math.max(dataSpan, 1);
    const padding = Math.max(span * 0.2, 1);
    return {
        scale: true,
        min: Math.floor(dataMin - padding),
        max: Math.ceil(dataMax + padding),
        splitNumber: 5,
    };
}

function renderSingleAnalysisChart(chartId, type, name, values, labels, unit) {
    const chartEl = $(chartId);
    if (!chartEl || !window.echarts) return;

    const chart = echarts.init(chartEl);
    const threshold = getAnalysisThreshold(type);
    const yAxisRange = getSingleChartYAxis(type, values, threshold);

    const series = {
        name,
        type: type === 'energy' ? 'bar' : 'line',
        data: values,
        smooth: type !== 'energy',
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { width: 3, color: '#5b6fcb' },
        itemStyle: { color: '#5b6fcb' },
        markPoint: {
            symbol: 'pin',
            symbolSize: 72,
            label: { color: '#fff', fontWeight: 800 },
            data: [{ type: 'max', name: '最大值' }],
        },
    };

    if (threshold?.yAxis !== undefined) {
        series.markLine = {
            symbol: ['circle', 'arrow'],
            data: [{
                yAxis: threshold.yAxis,
                name: threshold.label,
                lineStyle: { color: '#5b6fcb', type: 'dashed', width: 2 },
                label: { formatter: String(threshold.yAxis), color: '#444' },
            }],
        };
    }

    chart.setOption({
        tooltip: {
            trigger: 'axis',
            formatter(params) {
                const p = params?.[0];
                if (!p) return '';
                return `${escapeHtml(p.axisValue)}<br/>${p.marker}${escapeHtml(name)}：<b>${escapeHtml(formatNumber(p.value))}${escapeHtml(unit)}</b>`;
            },
        },
        grid: { left: 72, right: 48, top: 54, bottom: 70, containLabel: true },
        xAxis: {
            type: 'category',
            name: '时间',
            data: labels,
            axisLabel: { rotate: 45, hideOverlap: true },
        },
        yAxis: {
            type: 'value',
            name: `${TYPE_LABELS[type] || ''}${unit ? ` (${unit})` : ''}`,
            ...yAxisRange,
        },
        series: [series],
    }, true);

    window.setTimeout(() => chart.resize(), 50);
}

function formatNumber(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return '-';
    return Number.isInteger(number) ? String(number) : number.toFixed(2).replace(/\.?0+$/, '');
}


function showDataPointPopup(point) {
    document.querySelectorAll('.data-point-popup').forEach(el => el.remove());

    const popup = document.createElement('div');
    popup.className = 'data-point-popup';
    popup.innerHTML = `
        <div class="data-point-popup-content">
            <div class="data-point-popup-header">
                <h3>\u6570\u636e\u70b9\u8be6\u60c5</h3>
                <button class="data-point-popup-close" onclick="this.closest('.data-point-popup').remove()">\u00d7</button>
            </div>
            <div class="data-point-popup-body">
                <table class="data-point-table">
                    <tr><td class="label">\u6307\u6807</td><td class="value">${escapeHtml(point.seriesName)}</td></tr>
                    <tr><td class="label">\u7c7b\u578b</td><td class="value">${escapeHtml(TYPE_LABELS[point.type] || point.type || '-')}</td></tr>
                    <tr><td class="label">\u65f6\u95f4</td><td class="value">${escapeHtml(point.time || '-')}</td></tr>
                    <tr><td class="label">\u6570\u503c</td><td class="value highlight">${escapeHtml(fmt(point.value, point.unit))}</td></tr>
                    <tr><td class="label">\u5e8f\u53f7</td><td class="value">${escapeHtml(point.index)}</td></tr>
                </table>
            </div>
            <div class="data-point-popup-footer">
                <button class="popup-btn-close" onclick="this.closest('.data-point-popup').remove()">\u5173\u95ed</button>
            </div>
        </div>
    `;

    document.body.appendChild(popup);
}

document.addEventListener('DOMContentLoaded', () => {
    const queryBtn = $('dbQueryBtn');
    if (queryBtn) queryBtn.addEventListener('click', runMysqlQuery);

    const filterInput = $('filterInput');
    if (filterInput) filterInput.addEventListener('input', () => renderRows(state.rows));

    checkOllama();
});
