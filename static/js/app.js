// =============================================================================
// Tapo P110 Control Center — Frontend Multi-Theme Engine & Profile Manager
// =============================================================================

document.addEventListener("DOMContentLoaded", () => {
  // Global State
  let isDeviceOn = false;
  let currentYear = 2026;
  let currentMonth = 9; // Settembre (1-indexed)
  let activeTheme = localStorage.getItem("tapo_theme") || "cyber";
  let ws = null;
  let pollIntervalTimer = null;
  let historySamples = [];
  let monthlyData = [];
  let dailyData = [];

  // Theme Views
  const viewCyber = document.getElementById("view-cyber");
  const viewFluent = document.getElementById("view-fluent");
  const viewCockpit = document.getElementById("view-cockpit");
  const themeStylesheet = document.getElementById("themeStylesheet");
  const themeSelectors = document.querySelectorAll('[data-role="theme-selector"]');

  // Settings Modal Elements
  const settingsModal = document.getElementById("settingsModal");
  const btnCloseSettings = document.getElementById("btnCloseSettings");
  const btnCancelSettings = document.getElementById("btnCancelSettings");
  const btnSaveSettings = document.getElementById("btnSaveSettings");
  const inputIp = document.getElementById("inputIp");
  const inputEmail = document.getElementById("inputEmail");
  const inputPassword = document.getElementById("inputPassword");
  const inputDeviceName = document.getElementById("inputDeviceName");
  const checkDemoMode = document.getElementById("checkDemoMode");

  // Profile Toolbar Elements
  const btnResetDemo = document.getElementById("btnResetDemo");
  const btnExportProfile = document.getElementById("btnExportProfile");
  const btnImportProfile = document.getElementById("btnImportProfile");
  const fileProfileInput = document.getElementById("fileProfileInput");
  const appToast = document.getElementById("appToast");

  // Chart Instances
  let cyberWaveformChart = null;
  let fluentLiveChart = null;
  let fluentSparklineChart = null;
  let fluentMonthlyChart = null;
  let cockpitOscilloscopeChart = null;

  const monthNamesIt = [
    "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
    "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"
  ];
  const monthNamesShortEn = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
  ];

  // ---------------------------------------------------------------------------
  // 1. Toast Notification Helper
  // ---------------------------------------------------------------------------
  function showToast(message, duration = 3200) {
    if (!appToast) return;
    appToast.textContent = message;
    appToast.classList.add("show");
    setTimeout(() => {
      appToast.classList.remove("show");
    }, duration);
  }

  // ---------------------------------------------------------------------------
  // 2. Theme Switching Engine (Exact Screenshot Visual Fidelity)
  // ---------------------------------------------------------------------------
  function applyTheme(themeKey) {
    if (!["cyber", "fluent", "cockpit"].includes(themeKey)) {
      themeKey = "cyber";
    }
    activeTheme = themeKey;
    localStorage.setItem("tapo_theme", themeKey);
    document.body.setAttribute("data-theme", themeKey);
    themeStylesheet.href = `/static/css/theme-${themeKey}.css`;

    // Sync all dropdowns
    themeSelectors.forEach(sel => {
      sel.value = themeKey;
    });

    // Toggle active view
    viewCyber.classList.toggle("active", themeKey === "cyber");
    viewFluent.classList.toggle("active", themeKey === "fluent");
    viewCockpit.classList.toggle("active", themeKey === "cockpit");

    // Initialize or resize charts for the newly active view
    setTimeout(() => {
      initActiveViewCharts();
      if (historySamples.length > 0) {
        updateWaveformCharts(historySamples);
      }
      renderMonthlyViews();
    }, 80);
  }

  themeSelectors.forEach(sel => {
    sel.addEventListener("change", (e) => {
      applyTheme(e.target.value);
    });
  });

  // ---------------------------------------------------------------------------
  // 3. UI Update Engine (Binds State Across All 3 Views)
  // ---------------------------------------------------------------------------
  function updateUI(state) {
    if (!state) return;
    isDeviceOn = Boolean(state.device_on);

    const p = (state.active_power_w !== undefined && state.active_power_w !== null) ? Number(state.active_power_w) : 0.0;
    const v = (state.voltage_v !== undefined && state.voltage_v !== null) ? Number(state.voltage_v) : 0.0;
    const ma = (state.current_ma !== undefined && state.current_ma !== null) ? Number(state.current_ma) : 0.0;
    const kwh = (state.today_kwh !== undefined && state.today_kwh !== null) ? Number(state.today_kwh) : 0.00;
    const devName = state.device_name || "Tapo P110";
    const ip = state.device_ip || "127.0.0.1";
    const isConn = Boolean(state.is_connected);
    const isDemo = Boolean(state.demo_mode);

    // Formatted strings
    const powerStr = isDeviceOn ? (activeTheme === "cockpit" ? Math.round(p).toString() : p.toFixed(1)) : "0";
    const voltStr = isDeviceOn ? v.toFixed(3) : "0.000";
    const currMaStr = isDeviceOn ? Math.round(ma).toString() : "0";
    const currAmpStr = isDeviceOn ? (ma / 1000.0).toFixed(3) + " A" : "0.000 A";
    const energyStr = kwh.toFixed(2);

    // 1. Text elements across all views
    document.querySelectorAll(".val-power").forEach(el => el.textContent = powerStr);
    document.querySelectorAll(".val-voltage").forEach(el => el.textContent = voltStr);
    document.querySelectorAll(".val-current-ma").forEach(el => el.textContent = currMaStr);
    document.querySelectorAll(".val-current-amp").forEach(el => el.textContent = currAmpStr);
    document.querySelectorAll(".val-energy-today").forEach(el => el.textContent = energyStr);
    document.querySelectorAll(".device-name-display").forEach(el => el.textContent = devName);
    document.querySelectorAll(".ip-text").forEach(el => el.textContent = ip ? `IP: ${ip}` : "IP: --");
    document.querySelectorAll(".conn-text").forEach(el => {
      el.textContent = isDemo ? "Modalità Demo" : (isConn ? "Connesso" : "Disconnesso");
    });

    // 2. Power State: CYBER
    const cyberDialOuter = document.getElementById("cyberDialOuter");
    if (cyberDialOuter) {
      cyberDialOuter.classList.toggle("on", isDeviceOn);
      const stateLbl = cyberDialOuter.querySelector(".power-state-label");
      if (stateLbl) stateLbl.textContent = isDeviceOn ? "ON" : "OFF";
    }

    // 3. Power State: FLUENT
    const fluentPowerOuter = document.getElementById("fluentPowerOuter");
    const fluentSwitchPill = document.getElementById("fluentSwitchPill");
    const fluentSwitchText = document.getElementById("fluentSwitchText");
    const fluentStatusTitle = document.querySelector(".fluent-power-status-title");

    if (fluentPowerOuter) fluentPowerOuter.classList.toggle("on", isDeviceOn);
    if (fluentSwitchPill) fluentSwitchPill.classList.toggle("on", isDeviceOn);
    if (fluentSwitchText) fluentSwitchText.textContent = isDeviceOn ? "ON" : "OFF";
    if (fluentStatusTitle) {
      fluentStatusTitle.textContent = isDeviceOn ? "ACCESO" : "SPENTO";
      fluentStatusTitle.classList.toggle("off", !isDeviceOn);
    }

    // 4. Power State: COCKPIT
    const cockpitTurbineDial = document.getElementById("cockpitTurbineDial");
    if (cockpitTurbineDial) cockpitTurbineDial.classList.toggle("on", isDeviceOn);

    // Update semi-circular SVG gauge arc offsets in Cockpit (matching attached screenshot)
    updateCockpitGauges(p, v, ma, kwh, isDeviceOn);

    // Push live sample to waveform history
    addLiveSample(p);
  }

  function updateCockpitGauges(p, v, ma, kwh, on) {
    const arcPower = document.getElementById("cockpitArcPower");
    const arcVolt = document.getElementById("cockpitArcVoltage");
    const arcCurr = document.getElementById("cockpitArcCurrent");
    const arcEnergy = document.getElementById("cockpitArcEnergy");

    // Lunghezza semi-circolare con raggio 54: pi * 54 = 170px
    const totalDash = 170;
    if (!on) {
      if (arcPower) arcPower.style.strokeDashoffset = totalDash;
      if (arcVolt) arcVolt.style.strokeDashoffset = totalDash;
      if (arcCurr) arcCurr.style.strokeDashoffset = totalDash;
      if (arcEnergy) arcEnergy.style.strokeDashoffset = totalDash;
      return;
    }

    // Proportional dash offsets (0 = full gauge, 170 = empty)
    if (arcPower) {
      const ratio = Math.min(Math.max(p / 2500.0, 0), 1);
      arcPower.style.strokeDashoffset = totalDash - (ratio * totalDash);
    }
    if (arcVolt) {
      const ratio = Math.min(Math.max((v - 180) / 70.0, 0), 1);
      arcVolt.style.strokeDashoffset = totalDash - (ratio * totalDash);
    }
    if (arcCurr) {
      const ratio = Math.min(Math.max(ma / 8000.0, 0), 1);
      arcCurr.style.strokeDashoffset = totalDash - (ratio * totalDash);
    }
    if (arcEnergy) {
      const ratio = Math.min(Math.max(kwh / 20.0, 0), 1);
      arcEnergy.style.strokeDashoffset = totalDash - (ratio * totalDash);
    }
  }

  // ---------------------------------------------------------------------------
  // 4. Live Power Waveform Data Buffer & Chart.js Rendering
  // ---------------------------------------------------------------------------
  function addLiveSample(val) {
    const timeLabel = new Date().toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    historySamples.push({ timestamp: timeLabel, active_power_w: isDeviceOn ? val : 0.0 });
    if (historySamples.length > 30) historySamples.shift();
    updateWaveformCharts(historySamples);
  }

  function initActiveViewCharts() {
    // Cyber Neon Chart (Con riferimenti reali a numeri di Watt e orari di campionamento)
    const cyberCanvas = document.getElementById("cyberWaveformCanvas");
    if (cyberCanvas && !cyberWaveformChart) {
      const ctx = cyberCanvas.getContext("2d");
      const grad = ctx.createLinearGradient(0, 0, 0, 160);
      grad.addColorStop(0, "rgba(0, 242, 254, 0.45)");
      grad.addColorStop(1, "rgba(0, 242, 254, 0.0)");

      cyberWaveformChart = new Chart(ctx, {
        type: "line",
        data: {
          labels: Array(25).fill(""),
          datasets: [{
            data: Array(25).fill(0),
            borderColor: "#00f2fe",
            borderWidth: 2.5,
            backgroundColor: grad,
            fill: true,
            tension: 0.38,
            pointRadius: 2,
            pointBackgroundColor: "#00f2fe",
            pointBorderColor: "#ffffff",
            pointHoverRadius: 4
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: { duration: 250 },
          plugins: {
            legend: { display: false },
            tooltip: {
              enabled: true,
              callbacks: {
                title: (items) => `Orario: ${items[0].label}`,
                label: (item) => `Potenza: ${item.raw} W`
              }
            }
          },
          scales: {
            x: {
              display: true,
              grid: { color: "rgba(0, 242, 254, 0.08)" },
              ticks: {
                color: "rgba(0, 242, 254, 0.75)",
                font: { size: 9 },
                maxTicksLimit: 7
              }
            },
            y: {
              display: true,
              grid: { color: "rgba(0, 242, 254, 0.08)" },
              ticks: {
                color: "#00f2fe",
                font: { size: 9 },
                callback: (val) => val + " W"
              },
              suggestedMin: 0,
              suggestedMax: 1500
            }
          }
        }
      });
    }

    // Fluent Live Chart
    const fluentCanvas = document.getElementById("fluentLiveChartCanvas");
    if (fluentCanvas && !fluentLiveChart) {
      const ctx = fluentCanvas.getContext("2d");
      const grad = ctx.createLinearGradient(0, 0, 0, 140);
      grad.addColorStop(0, "rgba(56, 189, 248, 0.35)");
      grad.addColorStop(1, "rgba(56, 189, 248, 0.0)");

      fluentLiveChart = new Chart(ctx, {
        type: "line",
        data: {
          labels: Array(25).fill(""),
          datasets: [{
            data: Array(25).fill(0),
            borderColor: "#38bdf8",
            borderWidth: 2.5,
            backgroundColor: grad,
            fill: true,
            tension: 0.4,
            pointRadius: 0
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: {
              grid: { color: "rgba(255, 255, 255, 0.04)" },
              ticks: { color: "#64748b", font: { size: 9 }, maxTicksLimit: 8 }
            },
            y: {
              grid: { color: "rgba(255, 255, 255, 0.04)" },
              ticks: { color: "#64748b", font: { size: 9 } },
              suggestedMin: 0,
              suggestedMax: 10
            }
          }
        }
      });
    }

    // Fluent Sparkline in Power Card
    const sparkCanvas = document.getElementById("fluentSparklineCanvas");
    if (sparkCanvas && !fluentSparklineChart) {
      const ctx = sparkCanvas.getContext("2d");
      fluentSparklineChart = new Chart(ctx, {
        type: "line",
        data: {
          labels: Array(10).fill(""),
          datasets: [{
            data: [2, 3, 5, 4, 6, 7, 5, 6, 8, 7],
            borderColor: "#a855f7",
            borderWidth: 2,
            tension: 0.4,
            pointRadius: 0,
            fill: false
          }]
        },
        options: {
          responsive: false,
          maintainAspectRatio: false,
          plugins: { legend: { display: false }, tooltip: { enabled: false } },
          scales: { x: { display: false }, y: { display: false } }
        }
      });
    }

    // Fluent Monthly Daily Bars Chart
    const monthlyCanvas = document.getElementById("fluentMonthlyChartCanvas");
    if (monthlyCanvas && !fluentMonthlyChart) {
      const ctx = monthlyCanvas.getContext("2d");
      fluentMonthlyChart = new Chart(ctx, {
        type: "bar",
        data: {
          labels: Array.from({ length: 28 }, (_, i) => i + 1),
          datasets: [{
            data: Array(28).fill(0),
            backgroundColor: (ctx) => {
              const val = ctx.raw || 0;
              return val > 2.0 ? "#a855f7" : "#38bdf8";
            },
            borderRadius: 4
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                title: (items) => `${items[0].label} ${monthNamesIt[currentMonth - 1]}`,
                label: (item) => `${item.raw} kWh`
              }
            }
          },
          scales: {
            x: {
              grid: { display: false },
              ticks: { color: "#64748b", font: { size: 9 } }
            },
            y: {
              grid: { color: "rgba(255, 255, 255, 0.04)" },
              ticks: { color: "#64748b", font: { size: 9 } },
              suggestedMin: 0,
              suggestedMax: 10
            }
          }
        }
      });
    }

    // Cockpit Oscilloscope Canvas
    const oscCanvas = document.getElementById("cockpitOscilloscopeCanvas");
    if (oscCanvas && !cockpitOscilloscopeChart) {
      const ctx = oscCanvas.getContext("2d");
      cockpitOscilloscopeChart = new Chart(ctx, {
        type: "line",
        data: {
          labels: Array(30).fill(""),
          datasets: [{
            data: Array(30).fill(0),
            borderColor: "#10b981",
            borderWidth: 2,
            backgroundColor: "rgba(16, 185, 129, 0.15)",
            fill: true,
            tension: 0.35,
            pointRadius: 0
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: {
              grid: { color: "rgba(16, 185, 129, 0.12)" },
              ticks: { color: "#10b981", font: { size: 9 } }
            },
            y: {
              grid: { color: "rgba(16, 185, 129, 0.12)" },
              ticks: { color: "#10b981", font: { size: 9 } },
              suggestedMin: 0,
              suggestedMax: 1600
            }
          }
        }
      });
    }
  }

  function updateWaveformCharts(samples) {
    if (!samples || samples.length === 0) return;
    const labels = samples.map(s => s.timestamp);
    const dataVals = samples.map(s => s.active_power_w);

    // Dynamic Autoscaling
    const maxVal = Math.max(...dataVals, 1.0);
    const minVal = Math.min(...dataVals);
    const span = maxVal - minVal;
    const suggestedMax = maxVal + (span > 5 ? span * 0.2 : 4);
    const suggestedMin = Math.max(0, minVal - 2);

    if (cyberWaveformChart && activeTheme === "cyber") {
      cyberWaveformChart.data.labels = labels;
      cyberWaveformChart.data.datasets[0].data = dataVals;
      cyberWaveformChart.options.scales.y.suggestedMax = suggestedMax;
      cyberWaveformChart.options.scales.y.suggestedMin = suggestedMin;
      cyberWaveformChart.update("none");
    }

    if (fluentLiveChart && activeTheme === "fluent") {
      fluentLiveChart.data.labels = labels;
      fluentLiveChart.data.datasets[0].data = dataVals;
      fluentLiveChart.options.scales.y.suggestedMax = suggestedMax;
      fluentLiveChart.options.scales.y.suggestedMin = suggestedMin;
      fluentLiveChart.update("none");

      if (fluentSparklineChart) {
        fluentSparklineChart.data.datasets[0].data = dataVals.slice(-10);
        fluentSparklineChart.update("none");
      }
    }

    if (cockpitOscilloscopeChart && activeTheme === "cockpit") {
      cockpitOscilloscopeChart.data.labels = labels;
      cockpitOscilloscopeChart.data.datasets[0].data = dataVals;
      cockpitOscilloscopeChart.options.scales.y.suggestedMax = suggestedMax;
      cockpitOscilloscopeChart.options.scales.y.suggestedMin = suggestedMin;
      cockpitOscilloscopeChart.update("none");
    }
  }

  // ---------------------------------------------------------------------------
  // 5. Monthly & Daily History Data Visualizers
  // ---------------------------------------------------------------------------
  async function loadHistory() {
    try {
      const [resRecent, resMonths, resDays] = await Promise.all([
        fetch("/api/history/recent").then(r => r.json()),
        fetch(`/api/history/monthly?year=${currentYear}`).then(r => r.json()),
        fetch(`/api/history/days?year=${currentYear}&month=${currentMonth}`).then(r => r.json())
      ]);

      if (resRecent && resRecent.samples) {
        historySamples = resRecent.samples;
        updateWaveformCharts(historySamples);
      }

      if (resMonths && resMonths.months) {
        monthlyData = resMonths.months;
      }

      if (resDays && resDays.days) {
        dailyData = resDays.days;
      }

      renderMonthlyViews();
    } catch (e) {
      console.warn("Caricamento storico non riuscito:", e);
    }
  }

  async function loadMonthlyData() {
    try {
      const res = await fetch(`/api/history/monthly?year=${currentYear}`).then(r => r.json());
      if (res && res.months) {
        monthlyData = res.months;
        renderMonthlyViews();
      }
    } catch (e) {
      console.warn("Caricamento mesi non riuscito:", e);
    }
  }

  function renderMonthlyViews() {
    const now = new Date();
    const realYear = now.getFullYear();
    const realMonth = now.getMonth() + 1; // 1-12
    const yearSuffix = "'" + String(currentYear).slice(-2);

    // 1. Cyber Theme 12-Month Glowing Glass Pillars (Valori REALI e zero consumi futuri)
    const cyberYearDisplay = document.getElementById("cyberYearDisplay");
    if (cyberYearDisplay) cyberYearDisplay.textContent = String(currentYear);

    const pillarsContainer = document.getElementById("cyberMonthPillars");
    if (pillarsContainer) {
      pillarsContainer.innerHTML = "";
      
      // Calcola il massimo reale registrato nel database per scalare proporzionalmente le colonne
      const realMaxKwh = Math.max(...monthlyData.map(m => Number(m.kwh ?? m.total_kwh ?? 0)), 1.0);

      monthNamesShortEn.forEach((mName, idx) => {
        const monthNum = idx + 1;
        // Controllo mesi futuri rigoroso
        const isFuture = (currentYear > realYear) || (currentYear === realYear && monthNum > realMonth);
        const isCurrent = (currentYear === realYear && monthNum === realMonth);

        let val = 0.0;
        let pct = 0;

        if (!isFuture) {
          const mInfo = monthlyData.find(m => m.month === monthNum);
          if (mInfo) {
            val = Number(mInfo.kwh ?? mInfo.total_kwh ?? 0.0);
          }
          if (val > 0) {
            pct = Math.min(100, Math.max(8, (val / (realMaxKwh * 1.15)) * 100));
          }
        }

        const valLabel = isFuture ? "0.00" : (val > 0 ? (val >= 10 ? val.toFixed(1) : val.toFixed(2)) : "0.00");

        const col = document.createElement("div");
        col.className = `cyber-pillar-col ${monthNum === currentMonth ? 'active' : ''}`;
        col.innerHTML = `
          <div class="cyber-pillar-val" style="${isFuture ? 'opacity: 0.35;' : ''}">${valLabel} <span style="font-size:0.5rem; opacity:0.8;">kWh</span></div>
          <div class="cyber-pillar-track" title="${monthNamesIt[idx]} ${currentYear}: ${val.toFixed(2)} kWh">
            ${pct > 0 ? `<div class="cyber-pillar-fill" style="height: ${pct}%;"></div>` : ''}
          </div>
          <div class="cyber-pillar-month ${isCurrent ? 'current-month-highlight' : ''}">${monthNamesIt[idx].substring(0, 3)} ${yearSuffix}</div>
        `;
        col.addEventListener("click", () => {
          currentMonth = monthNum;
          loadHistory();
        });
        pillarsContainer.appendChild(col);
      });
    }

    // 2. Fluent Theme Monthly Bar Chart & Meta
    const fluentMonthText = document.getElementById("fluentCurrentMonthText");
    const fluentSummaryText = document.getElementById("fluentMonthSummaryText");
    const fluentBtnPrev = document.getElementById("fluentBtnPrev");
    const fluentBtnNext = document.getElementById("fluentBtnNext");

    if (fluentMonthText) fluentMonthText.textContent = `${monthNamesIt[currentMonth - 1]} ${currentYear}`;
    if (fluentBtnPrev) {
      const prevM = currentMonth === 1 ? 12 : currentMonth - 1;
      fluentBtnPrev.textContent = `‹ ${monthNamesIt[prevM - 1]}`;
    }
    if (fluentBtnNext) {
      const nextM = currentMonth === 12 ? 1 : currentMonth + 1;
      fluentBtnNext.textContent = `${monthNamesIt[nextM - 1]} ›`;
    }

    if (fluentMonthlyChart && dailyData) {
      const dayLabels = dailyData.map(d => d.day);
      const dayValues = dailyData.map(d => Number(d.kwh || 0));
      const totalM = dayValues.reduce((a, b) => a + b, 0);
      const daysCount = dayValues.filter(v => v > 0).length || 1;
      const avgD = totalM / daysCount;

      if (fluentSummaryText) {
        fluentSummaryText.textContent = `${totalM.toFixed(1)} kWh (media ${avgD.toFixed(2)} kWh/g)`;
      }

      fluentMonthlyChart.data.labels = dayLabels;
      fluentMonthlyChart.data.datasets[0].data = dayValues;
      fluentMonthlyChart.update();
    }

    // 3. Cockpit Theme Month Buttons List & Real Dynamic Telemetry Bars
    const cockpitMonthYearDisplay = document.getElementById("cockpitCurrentMonthYearDisplay");
    if (cockpitMonthYearDisplay) {
      cockpitMonthYearDisplay.textContent = `${monthNamesIt[currentMonth - 1]} ${currentYear}`;
    }

    // Calcolo valori reali per il mese selezionato in Cockpit
    const dayValuesCockpit = dailyData.map(d => Number(d.kwh || 0));
    const totalMonthKwh = dayValuesCockpit.reduce((a, b) => a + b, 0);
    const activeDaysCount = dayValuesCockpit.filter(v => v > 0).length || 1;
    const avgDailyKwh = totalMonthKwh / activeDaysCount;
    const peakDayKwh = dayValuesCockpit.length > 0 ? Math.max(...dayValuesCockpit) : 0;
    const quotaPct = Math.min(100, Math.round((totalMonthKwh / 40.0) * 100));

    const bTotal = document.getElementById("cockpitBarTotal");
    const vTotal = document.getElementById("cockpitValTotal");
    if (bTotal) bTotal.style.width = Math.min(100, Math.round((totalMonthKwh / 45.0) * 100)) + "%";
    if (vTotal) vTotal.textContent = totalMonthKwh.toFixed(1) + " kWh";

    const bAvg = document.getElementById("cockpitBarDailyAvg");
    const vAvg = document.getElementById("cockpitValDailyAvg");
    if (bAvg) bAvg.style.width = Math.min(100, Math.round((avgDailyKwh / 2.0) * 100)) + "%";
    if (vAvg) vAvg.textContent = avgDailyKwh.toFixed(2) + " kWh/d";

    const bPeak = document.getElementById("cockpitBarPeak");
    const vPeak = document.getElementById("cockpitValPeak");
    if (bPeak) bPeak.style.width = Math.min(100, Math.round((peakDayKwh / 3.0) * 100)) + "%";
    if (vPeak) vPeak.textContent = peakDayKwh.toFixed(2) + " kWh";

    const bQuota = document.getElementById("cockpitBarQuota");
    const vQuota = document.getElementById("cockpitValQuota");
    if (bQuota) bQuota.style.width = quotaPct + "%";
    if (vQuota) vQuota.textContent = quotaPct + "%";

    const cockpitMonthList = document.getElementById("cockpitMonthButtonsList");
    if (cockpitMonthList) {
      cockpitMonthList.innerHTML = "";
      monthNamesIt.forEach((mName, idx) => {
        const btn = document.createElement("button");
        btn.className = `cockpit-month-btn ${idx + 1 === currentMonth ? 'active' : ''}`;
        btn.textContent = mName;
        btn.addEventListener("click", () => {
          currentMonth = idx + 1;
          loadHistory();
        });
        cockpitMonthList.appendChild(btn);
      });
    }
  }

  async function loadDaysData() {
    try {
      const res = await fetch(`/api/history/days?year=${currentYear}&month=${currentMonth}`).then(r => r.json());
      if (res && res.days) {
        dailyData = res.days;
        renderMonthlyViews();
      }
    } catch (e) {
      console.warn("Errore caricamento giorni:", e);
    }
  }

  // Month navigation across themes (navigates months and updates year when crossing Jan/Dec)
  async function prevMonth() {
    if (currentMonth === 1) {
      currentMonth = 12;
      currentYear--;
    } else {
      currentMonth--;
    }
    await loadHistory();
  }

  async function nextMonth() {
    const now = new Date();
    const realYear = now.getFullYear();
    const realMonth = now.getMonth() + 1;
    if (currentYear > realYear || (currentYear === realYear && currentMonth >= realMonth)) {
      showToast("Nessun dato per date future");
      return;
    }

    if (currentMonth === 12) {
      currentMonth = 1;
      currentYear++;
    } else {
      currentMonth++;
    }
    await loadHistory();
  }

  // Year Navigation
  async function prevCyberYear() {
    currentYear--;
    await loadHistory();
  }

  async function nextCyberYear() {
    const realYear = new Date().getFullYear();
    if (currentYear >= realYear) {
      showToast("Nessun dato per anni futuri");
      return;
    }
    currentYear++;
    await loadHistory();
  }

  document.querySelectorAll(".fluent-nav-btn.btn-month-prev, .cockpit-arrow-btn.btn-month-prev, #btnCockpitPrevMonth").forEach(b => {
    b.addEventListener("click", prevMonth);
  });
  document.querySelectorAll(".fluent-nav-btn.btn-month-next, .cockpit-arrow-btn.btn-month-next, #btnCockpitNextMonth").forEach(b => {
    b.addEventListener("click", nextMonth);
  });

  const btnCyberPrev = document.getElementById("btnCyberYearPrev");
  const btnCyberNext = document.getElementById("btnCyberYearNext");
  if (btnCyberPrev) btnCyberPrev.addEventListener("click", prevCyberYear);
  if (btnCyberNext) btnCyberNext.addEventListener("click", nextCyberYear);

  // --- MOUSE WHEEL SCROLL EVENT HANDLERS ---
  let isWheelScrolling = false;
  function triggerWheelScroll(delta, isYearNav) {
    if (isWheelScrolling) return;
    isWheelScrolling = true;
    setTimeout(() => { isWheelScrolling = false; }, 220);

    if (isYearNav) {
      if (delta < 0) prevCyberYear();
      else nextCyberYear();
    } else {
      if (delta < 0) prevMonth();
      else nextMonth();
    }
  }

  // 1. Cyber Neon Wheel Scroll
  const cyberMonthsSec = document.querySelector(".cyber-months-section");
  if (cyberMonthsSec) {
    cyberMonthsSec.addEventListener("wheel", (e) => {
      e.preventDefault();
      triggerWheelScroll(e.deltaY || e.deltaX, true);
    }, { passive: false });
  }

  // 2. Pro Cockpit Wheel Scroll
  const cockpitAnalyticsCard = document.querySelector(".cockpit-analytics-card");
  if (cockpitAnalyticsCard) {
    cockpitAnalyticsCard.addEventListener("wheel", (e) => {
      e.preventDefault();
      triggerWheelScroll(e.deltaY || e.deltaX, false);
    }, { passive: false });
  }

  // 3. Windows 11 Fluent Wheel Scroll
  const fluentChartBox = document.querySelector(".fluent-chart-box");
  if (fluentChartBox) {
    fluentChartBox.addEventListener("wheel", (e) => {
      e.preventDefault();
      triggerWheelScroll(e.deltaY || e.deltaX, false);
    }, { passive: false });
  }

  // ---------------------------------------------------------------------------
  // 6. Master Power Toggle Action (Works for Any Dial, Knob or Switch)
  // ---------------------------------------------------------------------------
  async function togglePower() {
    const newState = !isDeviceOn;
    try {
      const res = await fetch("/api/power", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ state: newState })
      }).then(r => r.json());

      if (res && res.state) {
        updateUI(res.state);
      }
    } catch (err) {
      console.error("Errore toggle power:", err);
    }
  }

  document.querySelectorAll(".btn-power-toggle").forEach(btn => {
    btn.addEventListener("click", togglePower);
  });

  // ---------------------------------------------------------------------------
  // 7. Settings Modal & Profile Toolbar (3 Requested Profile Buttons)
  // ---------------------------------------------------------------------------
  document.querySelectorAll(".btn-trigger-settings").forEach(btn => {
    btn.addEventListener("click", () => {
      loadSettingsIntoModal();
      settingsModal.classList.add("open");
    });
  });

  if (btnCloseSettings) btnCloseSettings.addEventListener("click", () => settingsModal.classList.remove("open"));
  if (btnCancelSettings) btnCancelSettings.addEventListener("click", () => settingsModal.classList.remove("open"));

  // Settings Checkboxes (Figura 4 & Gadget)
  const checkMinimizeTray = document.getElementById("checkMinimizeTray");
  const checkMinimizeStart = document.getElementById("checkMinimizeStart");
  const checkStartWindows = document.getElementById("checkStartWindows");
  const checkShowGadget = document.getElementById("checkShowGadget");

  async function loadSettingsIntoModal() {
    try {
      const cfg = await fetch(`/api/settings?_t=${Date.now()}`, { cache: "no-store" }).then(r => r.json());
      inputIp.value = cfg.ip || "";
      inputEmail.value = cfg.email || "";
      inputPassword.value = cfg.password_set ? "******" : "";
      inputDeviceName.value = cfg.device_name || "Tapo P110";
      checkDemoMode.checked = Boolean(cfg.demo_mode);
      if (checkMinimizeTray) checkMinimizeTray.checked = Boolean(cfg.minimize_to_tray);
      if (checkMinimizeStart) checkMinimizeStart.checked = Boolean(cfg.minimize_on_start);
      if (checkStartWindows) checkStartWindows.checked = Boolean(cfg.start_with_windows);
      if (checkShowGadget) checkShowGadget.checked = Boolean(cfg.show_desktop_gadget);
    } catch (e) {
      console.warn("Impossibile caricare impostazioni correnti:", e);
    }
  }

  // --- BUTTON 1: Svuota Campi & Abilita Demo ---
  if (btnResetDemo) {
    btnResetDemo.addEventListener("click", async () => {
      inputIp.value = "";
      inputEmail.value = "";
      inputPassword.value = "";
      checkDemoMode.checked = true;
      if (checkMinimizeTray) checkMinimizeTray.checked = false;
      if (checkMinimizeStart) checkMinimizeStart.checked = false;
      if (checkStartWindows) checkStartWindows.checked = false;
      if (checkShowGadget) checkShowGadget.checked = false;

      // Salva immediatamente al backend
      await submitSettings({
        ip: "",
        email: "",
        password: "",
        device_name: inputDeviceName.value.trim() || "Tapo P110",
        demo_mode: true,
        minimize_to_tray: false,
        minimize_on_start: false,
        start_with_windows: false,
        show_desktop_gadget: false
      });

      showToast("Campi svuotati e Modalità Demo attivata!");
    });
  }

  // --- BUTTON 2: Salva Profilo (Salva anche la cronologia consumi nel file JSON) ---
  if (btnExportProfile) {
    btnExportProfile.addEventListener("click", async () => {
      const profileData = {
        ip: inputIp.value.trim(),
        email: inputEmail.value.trim(),
        password: inputPassword.value === "******" ? "" : inputPassword.value,
        device_name: inputDeviceName.value.trim() || "Tapo P110",
        demo_mode: false,
        theme: activeTheme,
        minimize_to_tray: checkMinimizeTray ? checkMinimizeTray.checked : false,
        minimize_on_start: checkMinimizeStart ? checkMinimizeStart.checked : false,
        start_with_windows: checkStartWindows ? checkStartWindows.checked : false,
        show_desktop_gadget: checkShowGadget ? checkShowGadget.checked : false
      };

      try {
        const res = await fetch("/api/profile/save-dialog", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(profileData)
        }).then(r => r.json());

        if (res && res.success) {
          showToast(`Profilo e cronologia grafici salvati in: ${res.filename}`);
          return;
        } else if (res && res.cancelled) {
          return;
        }
      } catch (err) {
        console.warn("Finestra dialogo nativa non disponibile, uso download diretto:", err);
      }

      // Fallback con download browser classico se la chiamata nativa fallisse
      const blob = new Blob([JSON.stringify(profileData, null, 4)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "settings.json";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      showToast("Profilo esportato!");
    });
  }

  // --- BUTTON 3: Carica Profilo (Ripristina credenziali, tema, gadget e cronologia grafici) ---
  if (btnImportProfile) {
    btnImportProfile.addEventListener("click", async () => {
      try {
        const res = await fetch("/api/profile/load-dialog", {
          method: "POST",
          headers: { "Content-Type": "application/json" }
        }).then(r => r.json());

        if (res && res.success && res.config) {
          // 1. Popola SUBITO tutti i campi del modal con i dati caricati!
          inputIp.value = res.config.ip || "";
          inputEmail.value = res.config.email || "";
          inputPassword.value = res.config.password ? "******" : "";
          inputDeviceName.value = res.config.device_name || "Tapo P110";
          
          // REQUISITO CRITICO: quando si richiama il file la modalità demo deve essere disattivata!
          checkDemoMode.checked = false;

          if (checkMinimizeTray && res.config.minimize_to_tray !== undefined) checkMinimizeTray.checked = Boolean(res.config.minimize_to_tray);
          if (checkMinimizeStart && res.config.minimize_on_start !== undefined) checkMinimizeStart.checked = Boolean(res.config.minimize_on_start);
          if (checkStartWindows && res.config.start_with_windows !== undefined) checkStartWindows.checked = Boolean(res.config.start_with_windows);
          if (checkShowGadget && res.config.show_desktop_gadget !== undefined) checkShowGadget.checked = Boolean(res.config.show_desktop_gadget);

          // 2. Applica ISTANTANEAMENTE il tema salvato nel profilo senza riavviare!
          if (res.config.theme) {
            applyTheme(res.config.theme);
          }

          // 3. Aggiorna nome dispositivo nell'intestazione
          const dName = res.config.device_name || "Tapo P110";
          document.querySelectorAll(".header-title, .device-title, #headerDeviceName").forEach(el => {
            el.textContent = dName;
          });

          // 4. Aggiorna stato live dei componenti
          if (res.state) {
            updateUI(res.state);
          }

          // 5. Ricarica la cronologia consumi dal DB appena aggiornato
          await loadHistory();

          // Lasciamo il modal aperto così l'utente vede direttamente i campi compilati!
          showToast(`Profilo "${res.filename}" caricato con successo!`);
          return;
        } else if (res && res.cancelled) {
          return;
        }
      } catch (err) {
        console.warn("Finestra dialogo nativa non disponibile, uso file input:", err);
      }

      // Fallback con file input standard HTML se il dialogo nativo non risponde
      if (fileProfileInput) fileProfileInput.click();
    });

    if (fileProfileInput) {
      fileProfileInput.addEventListener("change", (e) => {
        const file = e.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = async (event) => {
          try {
            const cfg = JSON.parse(event.target.result);
            const res = await fetch("/api/profile/load-data", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(cfg)
            }).then(r => r.json());

            if (res && res.success && res.config) {
              inputIp.value = res.config.ip || "";
              inputEmail.value = res.config.email || "";
              inputPassword.value = res.config.password ? "******" : "";
              inputDeviceName.value = res.config.device_name || "Tapo P110";
              checkDemoMode.checked = false;

              if (checkMinimizeTray && res.config.minimize_to_tray !== undefined) checkMinimizeTray.checked = Boolean(res.config.minimize_to_tray);
              if (checkMinimizeStart && res.config.minimize_on_start !== undefined) checkMinimizeStart.checked = Boolean(res.config.minimize_on_start);
              if (checkStartWindows && res.config.start_with_windows !== undefined) checkStartWindows.checked = Boolean(res.config.start_with_windows);
              if (checkShowGadget && res.config.show_desktop_gadget !== undefined) checkShowGadget.checked = Boolean(res.config.show_desktop_gadget);

              if (res.config.theme) {
                applyTheme(res.config.theme);
              }

              const dName = res.config.device_name || "Tapo P110";
              document.querySelectorAll(".header-title, .device-title, #headerDeviceName").forEach(el => {
                el.textContent = dName;
              });

              if (res.state) {
                updateUI(res.state);
              }

              await loadHistory();
              showToast(`Profilo "${file.name}" caricato con successo!`);
            } else {
              alert("Errore durante il caricamento del profilo.");
            }
          } catch (err) {
            alert("File JSON non valido o corrotto: " + err.message);
          }
          fileProfileInput.value = "";
        };
        reader.readAsText(file);
      });
    }
  }

  // Manual Save and Connect Button
  if (btnSaveSettings) {
    btnSaveSettings.addEventListener("click", async () => {
      await submitSettings({
        ip: inputIp.value.trim(),
        email: inputEmail.value.trim(),
        password: inputPassword.value,
        device_name: inputDeviceName.value.trim() || "Tapo P110",
        demo_mode: checkDemoMode.checked,
        minimize_to_tray: checkMinimizeTray ? checkMinimizeTray.checked : false,
        minimize_on_start: checkMinimizeStart ? checkMinimizeStart.checked : false,
        start_with_windows: checkStartWindows ? checkStartWindows.checked : false,
        show_desktop_gadget: checkShowGadget ? checkShowGadget.checked : false
      });
      settingsModal.classList.remove("open");
      showToast("Configurazione salvata con successo!");
    });
  }

  async function submitSettings(payload) {
    try {
      const res = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      }).then(r => r.json());

      if (res && res.state) {
        updateUI(res.state);
      }
    } catch (err) {
      console.error("Errore salvataggio impostazioni:", err);
      showToast("Errore di connessione al backend");
    }
  }

  // ---------------------------------------------------------------------------
  // 8. WebSocket Telemetry & Fallback Polling
  // ---------------------------------------------------------------------------
  function connectWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "telemetry" && data.payload) {
          updateUI(data.payload);
        }
      } catch (err) {
        console.error("Errore parsing telemetry:", err);
      }
    };

    ws.onclose = () => {
      setTimeout(connectWebSocket, 2500);
    };

    ws.onerror = () => {
      ws.close();
    };
  }

  function startFallbackPolling() {
    if (pollIntervalTimer) clearInterval(pollIntervalTimer);
    pollIntervalTimer = setInterval(async () => {
      try {
        const state = await fetch("/api/status").then(r => r.json());
        if (state) updateUI(state);
      } catch (e) {
        // Silently retry
      }
    }, 2000);
  }

  // ---------------------------------------------------------------------------
  // 9. Initial Boot
  // ---------------------------------------------------------------------------
  applyTheme(activeTheme);
  fetch("/api/status").then(r => r.json()).then(st => updateUI(st)).catch(() => {});
  loadHistory();
  connectWebSocket();
  startFallbackPolling();
});
