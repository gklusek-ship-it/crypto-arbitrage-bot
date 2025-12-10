let pnlChart = null;

async function fetchJSON(url) {
    try {
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
    } catch (error) {
        console.error(`Error fetching ${url}:`, error);
        return null;
    }
}

function formatCurrency(value) {
    const num = parseFloat(value) || 0;
    const prefix = num >= 0 ? '$' : '-$';
    return prefix + Math.abs(num).toFixed(2);
}

function formatDate(isoString) {
    if (!isoString) return '--';
    const date = new Date(isoString);
    return date.toLocaleString();
}

function formatShortDate(dateString) {
    if (!dateString) return '--';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

async function updateFees() {
    const fees = await fetchJSON('/api/fees');
    const container = document.getElementById('feesGrid');
    
    if (!fees || fees.length === 0) {
        container.innerHTML = '<p class="no-data">No fee data available</p>';
        return;
    }
    
    container.innerHTML = fees.map(fee => `
        <div class="fee-card">
            <h3>${fee.exchange.toUpperCase()}</h3>
            <div class="fee-row">
                <span class="fee-label">Maker:</span>
                <span class="fee-value">${fee.maker.toFixed(2)}%</span>
            </div>
            <div class="fee-row">
                <span class="fee-label">Taker:</span>
                <span class="fee-value">${fee.taker.toFixed(2)}%</span>
            </div>
        </div>
    `).join('');
}

async function updateShadowTrading() {
    const [stats, trades] = await Promise.all([
        fetchJSON('/api/shadow/stats'),
        fetchJSON('/api/shadow/trades')
    ]);
    
    if (stats) {
        document.getElementById('shadowTrades').textContent = stats.total_trades || 0;
        
        const shadowPnl = document.getElementById('shadowPnl');
        shadowPnl.textContent = formatCurrency(stats.total_pnl_usd);
        shadowPnl.className = 'stat-value ' + ((stats.total_pnl_usd || 0) >= 0 ? 'positive' : 'negative');
        
        document.getElementById('shadowWinRate').textContent = (stats.win_rate || 0).toFixed(1) + '%';
        document.getElementById('shadowAvgPnl').textContent = formatCurrency(stats.avg_pnl_per_trade);
    }
    
    const tbody = document.getElementById('shadowTradesBody');
    if (!trades || trades.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="no-data">No shadow trades yet</td></tr>';
        return;
    }
    
    tbody.innerHTML = trades.slice(0, 20).map(trade => {
        const pnlClass = (trade.pnl_usd || 0) >= 0 ? 'positive' : 'negative';
        return `
            <tr>
                <td>${formatDate(trade.timestamp)}</td>
                <td>${trade.symbol || '--'}</td>
                <td>${trade.buy_exchange || '--'}</td>
                <td>${trade.sell_exchange || '--'}</td>
                <td>${(trade.spread_percent || 0).toFixed(3)}%</td>
                <td class="${pnlClass}">${formatCurrency(trade.pnl_usd)}</td>
            </tr>
        `;
    }).join('');
}

async function updateSummary() {
    const stats = await fetchJSON('/api/stats/summary');
    if (!stats) return;

    document.getElementById('totalTrades').textContent = stats.total_trades || 0;
    
    const totalPnl = document.getElementById('totalPnl');
    totalPnl.textContent = formatCurrency(stats.total_pnl_usd);
    totalPnl.className = 'stat-value ' + (stats.total_pnl_usd >= 0 ? 'positive' : 'negative');

    document.getElementById('winRate').textContent = (stats.win_rate || 0).toFixed(1) + '%';
    document.getElementById('avgPnl').textContent = formatCurrency(stats.avg_pnl_per_trade);

    document.getElementById('bestTrade').textContent = formatCurrency(stats.best_trade_pnl);
    document.getElementById('worstTrade').textContent = formatCurrency(stats.worst_trade_pnl);
}

async function updateDailyPnlChart() {
    const data = await fetchJSON('/api/stats/daily_pnl');
    if (!data) return;

    const labels = data.map(d => formatShortDate(d.date));
    const pnlData = data.map(d => d.total_pnl || 0);
    const colors = pnlData.map(v => v >= 0 ? 'rgba(75, 192, 75, 0.8)' : 'rgba(255, 99, 99, 0.8)');
    const borderColors = pnlData.map(v => v >= 0 ? 'rgba(75, 192, 75, 1)' : 'rgba(255, 99, 99, 1)');

    const ctx = document.getElementById('dailyPnlChart').getContext('2d');

    if (pnlChart) {
        pnlChart.data.labels = labels;
        pnlChart.data.datasets[0].data = pnlData;
        pnlChart.data.datasets[0].backgroundColor = colors;
        pnlChart.data.datasets[0].borderColor = borderColors;
        pnlChart.update();
    } else {
        pnlChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Daily PnL (USD)',
                    data: pnlData,
                    backgroundColor: colors,
                    borderColor: borderColors,
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        labels: {
                            color: '#e0e0e0'
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: { color: '#b0b0b0' },
                        grid: { color: 'rgba(255,255,255,0.1)' }
                    },
                    y: {
                        ticks: { 
                            color: '#b0b0b0',
                            callback: function(value) {
                                return '$' + value.toFixed(2);
                            }
                        },
                        grid: { color: 'rgba(255,255,255,0.1)' }
                    }
                }
            }
        });
    }
}

async function updateTradesTable() {
    const trades = await fetchJSON('/api/trades/recent');
    const tbody = document.getElementById('tradesBody');

    if (!trades || trades.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="no-data">No trades yet</td></tr>';
        return;
    }

    tbody.innerHTML = trades.map(trade => {
        const pnlClass = (trade.pnl_usd || 0) >= 0 ? 'positive' : 'negative';
        const modeLabel = trade.dry_run ? 'DRY RUN' : 'LIVE';
        const modeClass = trade.dry_run ? 'mode-dry' : 'mode-live';

        return `
            <tr>
                <td>${formatDate(trade.timestamp)}</td>
                <td class="symbol">${trade.symbol || '--'}</td>
                <td>${trade.buy_exchange || '--'}</td>
                <td>${trade.sell_exchange || '--'}</td>
                <td>${(trade.amount || 0).toFixed(6)}</td>
                <td>${(trade.net_spread_percent || 0).toFixed(3)}%</td>
                <td class="${pnlClass}">${formatCurrency(trade.pnl_usd)}</td>
                <td><span class="${modeClass}">${modeLabel}</span></td>
            </tr>
        `;
    }).join('');
}

function updateLastUpdateTime() {
    const now = new Date();
    document.getElementById('lastUpdate').textContent = 'Last update: ' + now.toLocaleTimeString();
    
    const indicator = document.getElementById('refreshIndicator');
    indicator.classList.add('active');
    setTimeout(() => indicator.classList.remove('active'), 500);
}

async function refreshDashboard() {
    await Promise.all([
        updateSummary(),
        updateDailyPnlChart(),
        updateTradesTable(),
        updateFees(),
        updateShadowTrading()
    ]);
    updateLastUpdateTime();
}

// =============================================================================
// PARAMETER MANAGEMENT
// =============================================================================
// To add a new parameter:
// 1. Add it to DEFAULT_PARAMETERS in db.py (backend)
// 2. The parameter will automatically appear in the dashboard
// 3. Min/max validation is handled by the backend

async function loadParameters() {
    const params = await fetchJSON('/api/params');
    const grid = document.getElementById('paramsGrid');
    
    if (!params || params.length === 0) {
        grid.innerHTML = '<p class="no-data">No parameters configured</p>';
        return;
    }
    
    grid.innerHTML = params.map(param => {
        const step = param.max_value < 1 ? 0.01 : (param.max_value < 100 ? 0.1 : 1);
        return `
            <div class="param-card" data-param="${param.name}">
                <div class="param-header">
                    <label class="param-name">${formatParamName(param.name)}</label>
                    <span class="param-range">(${param.min_value} - ${param.max_value})</span>
                </div>
                <p class="param-desc">${param.description || ''}</p>
                <div class="param-controls">
                    <input type="number" 
                           class="param-input" 
                           id="input-${param.name}"
                           value="${param.value}"
                           min="${param.min_value}"
                           max="${param.max_value}"
                           step="${step}">
                    <button class="param-save" onclick="saveParameter('${param.name}')">Save</button>
                </div>
                <span class="param-updated">Last: ${formatDate(param.updated_at)}</span>
            </div>
        `;
    }).join('');
}

function formatParamName(name) {
    return name.replace(/_/g, ' ').replace(/USD/g, '($)').replace(/PERCENT/g, '(%)');
}

async function saveParameter(name) {
    const input = document.getElementById(`input-${name}`);
    const value = parseFloat(input.value);
    const statusEl = document.getElementById('paramsStatus');
    
    if (isNaN(value)) {
        showParamStatus('Invalid number', 'error');
        return;
    }
    
    const min = parseFloat(input.min);
    const max = parseFloat(input.max);
    if (value < min || value > max) {
        showParamStatus(`Value must be between ${min} and ${max}`, 'error');
        return;
    }
    
    try {
        const response = await fetch('/api/params/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, value })
        });
        
        const result = await response.json();
        
        if (result.success) {
            showParamStatus(`${formatParamName(name)} updated successfully`, 'success');
            const card = document.querySelector(`[data-param="${name}"]`);
            if (card) {
                const updated = card.querySelector('.param-updated');
                updated.textContent = `Last: ${new Date().toLocaleString()}`;
            }
        } else {
            showParamStatus(result.message || 'Update failed', 'error');
        }
    } catch (error) {
        console.error('Error saving parameter:', error);
        showParamStatus('Network error', 'error');
    }
}

function showParamStatus(message, type) {
    const statusEl = document.getElementById('paramsStatus');
    statusEl.textContent = message;
    statusEl.className = `params-status ${type}`;
    setTimeout(() => {
        statusEl.textContent = '';
        statusEl.className = 'params-status';
    }, 3000);
}

document.addEventListener('DOMContentLoaded', () => {
    refreshDashboard();
    loadParameters();
    setInterval(refreshDashboard, 30000);
});
