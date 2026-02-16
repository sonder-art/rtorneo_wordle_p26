/**
 * Chart helpers using Chart.js for the Wordle Tournament Dashboard.
 * EVA-02 dark theme compatible.
 */

// Set Chart.js global defaults for dark theme
Chart.defaults.color = '#ccc';
Chart.defaults.borderColor = '#2a2a4e';

const COLORS = [
  '#c62828', '#e65100', '#ffd600', '#4caf50', '#1e88e5',
  '#ab47bc', '#ff7043', '#26c6da', '#8d6e63', '#78909c'
];

/**
 * Create a bar chart showing guess distribution for a single strategy.
 */
function createDistributionChart(canvas, strategyName, distribution, maxGuesses) {
  const labels = [];
  const data = [];
  for (let i = 1; i <= maxGuesses; i++) {
    labels.push(String(i));
    data.push(distribution[String(i)] || 0);
  }
  if (distribution['failed']) {
    labels.push('F');
    data.push(distribution['failed']);
  }

  return new Chart(canvas, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: strategyName,
        data: data,
        backgroundColor: COLORS[0] + 'cc',
        borderColor: COLORS[0],
        borderWidth: 1
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        title: {
          display: true,
          text: strategyName,
          font: { size: 12 },
          color: '#ff8a65'
        },
        legend: { display: false }
      },
      scales: {
        x: {
          title: { display: true, text: 'Intentos', color: '#aaa' },
          ticks: { color: '#999' },
          grid: { color: '#1e1e38' }
        },
        y: {
          title: { display: true, text: 'Cantidad', color: '#aaa' },
          ticks: { color: '#999' },
          grid: { color: '#1e1e38' },
          beginAtZero: true
        }
      }
    }
  });
}

/**
 * Create an overlaid bar chart comparing multiple strategies.
 */
function createComparisonChart(canvas, strategies, maxGuesses) {
  const labels = [];
  for (let i = 1; i <= maxGuesses; i++) labels.push(String(i));
  labels.push('F');

  const datasets = strategies.map((s, idx) => ({
    label: s.name,
    data: labels.map(l => {
      if (l === 'F') return (s.distribution['failed'] || 0);
      return (s.distribution[l] || 0);
    }),
    backgroundColor: COLORS[idx % COLORS.length] + '99',
    borderColor: COLORS[idx % COLORS.length],
    borderWidth: 1
  }));

  return new Chart(canvas, {
    type: 'bar',
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      aspectRatio: 2,
      plugins: {
        title: {
          display: true,
          text: 'Comparacion de Distribucion de Intentos',
          font: { size: 14 },
          color: '#ff8a65'
        },
        legend: {
          labels: { color: '#ccc' }
        }
      },
      scales: {
        x: {
          title: { display: true, text: 'Intentos', color: '#aaa' },
          ticks: { color: '#999' },
          grid: { color: '#1e1e38' }
        },
        y: {
          title: { display: true, text: 'Cantidad', color: '#aaa' },
          ticks: { color: '#999' },
          grid: { color: '#1e1e38' },
          beginAtZero: true
        }
      }
    }
  });
}
