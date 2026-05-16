import './VanillaDateRangePicker.css';

/**
 * Initializes a date range picker inside the specified container.
 * @param {HTMLElement} container The DOM element to mount the picker.
 * @param {Object} options Configuration options.
 */
export function initDateRangePicker(container, options = {}) {
  // State
  let drFrom = options.initialFrom || null;
  let drTo = options.initialTo || null;
  let drHover = null;
  
  // Calendars tracking
  let leftDate = drFrom ? new Date(drFrom) : new Date();
  leftDate.setDate(1); // Set to first of month
  
  let rightDate = new Date(leftDate);
  rightDate.setMonth(rightDate.getMonth() + 1);

  // Active preset
  let activePreset = null;

  // DOM Elements setup
  container.innerHTML = '';
  container.classList.add('vdrp-wrapper');

  // SVG Icons
  const calendarIcon = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>`;
  const clearIcon = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`;
  const chevronLeft = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"></polyline></svg>`;
  const chevronRight = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>`;

  // 1. Build Trigger
  const trigger = document.createElement('div');
  trigger.className = 'vdrp-trigger';
  trigger.innerHTML = `
    <span class="vdrp-trigger-icon">${calendarIcon}</span>
    <span class="vdrp-trigger-text placeholder">Seleccionar fechas...</span>
    <button type="button" class="vdrp-trigger-clear">${clearIcon}</button>
  `;
  container.appendChild(trigger);

  const triggerText = trigger.querySelector('.vdrp-trigger-text');
  const triggerClear = trigger.querySelector('.vdrp-trigger-clear');

  // 2. Build Popover
  const popover = document.createElement('div');
  popover.className = 'vdrp-popover';
  popover.innerHTML = `
    <div class="vdrp-popover-body">
      <div class="vdrp-presets">
        <button type="button" class="vdrp-preset-btn" data-preset="today">Hoy</button>
        <button type="button" class="vdrp-preset-btn" data-preset="yesterday">Ayer</button>
        <button type="button" class="vdrp-preset-btn" data-preset="thisWeek">Esta semana</button>
        <button type="button" class="vdrp-preset-btn" data-preset="lastWeek">Semana pasada</button>
        <button type="button" class="vdrp-preset-btn" data-preset="thisMonth">Este mes</button>
        <button type="button" class="vdrp-preset-btn" data-preset="lastMonth">Mes pasado</button>
        <button type="button" class="vdrp-preset-btn" data-preset="last30">Últimos 30 días</button>
        <button type="button" class="vdrp-preset-btn" data-preset="last90">Últimos 90 días</button>
      </div>
      <div class="vdrp-calendars">
        <div class="vdrp-month vdrp-month-left">
          <div class="vdrp-month-header">
            <button type="button" class="vdrp-month-nav vdrp-prev-month">${chevronLeft}</button>
            <span class="vdrp-month-label"></span>
            <div style="width: 28px;"></div> <!-- placeholder -->
          </div>
          <div class="vdrp-weekdays">
            <span>Lu</span><span>Ma</span><span>Mi</span><span>Ju</span><span>Vi</span><span>Sá</span><span>Do</span>
          </div>
          <div class="vdrp-days"></div>
        </div>
        <div class="vdrp-month vdrp-month-right">
          <div class="vdrp-month-header">
            <div style="width: 28px;"></div> <!-- placeholder -->
            <span class="vdrp-month-label"></span>
            <button type="button" class="vdrp-month-nav vdrp-next-month">${chevronRight}</button>
          </div>
          <div class="vdrp-weekdays">
            <span>Lu</span><span>Ma</span><span>Mi</span><span>Ju</span><span>Vi</span><span>Sá</span><span>Do</span>
          </div>
          <div class="vdrp-days"></div>
        </div>
      </div>
    </div>
    <div class="vdrp-footer">
      <span class="vdrp-footer-text">Selecciona una fecha de inicio</span>
      <div class="vdrp-footer-actions">
        <button type="button" class="vdrp-btn vdrp-btn-cancel">Cancelar</button>
        <button type="button" class="vdrp-btn vdrp-btn-apply">Aplicar</button>
      </div>
    </div>
  `;
  container.appendChild(popover);

  const leftDaysContainer = popover.querySelector('.vdrp-month-left .vdrp-days');
  const rightDaysContainer = popover.querySelector('.vdrp-month-right .vdrp-days');
  const leftLabel = popover.querySelector('.vdrp-month-left .vdrp-month-label');
  const rightLabel = popover.querySelector('.vdrp-month-right .vdrp-month-label');
  const footerText = popover.querySelector('.vdrp-footer-text');
  const presetsContainer = popover.querySelector('.vdrp-presets');

  // Format Helpers
  const formatMonthYear = (date) => {
    return new Intl.DateTimeFormat('es-ES', { month: 'long', year: 'numeric' }).format(date).replace(/^\w/, c => c.toUpperCase());
  };

  const formatDate = (date) => {
    return new Intl.DateTimeFormat('es-ES', { day: 'numeric', month: 'short', year: 'numeric' }).format(date);
  };

  const isSameDay = (d1, d2) => {
    if (!d1 || !d2) return false;
    return d1.getFullYear() === d2.getFullYear() &&
           d1.getMonth() === d2.getMonth() &&
           d1.getDate() === d2.getDate();
  };

  const isBefore = (d1, d2) => {
    if (!d1 || !d2) return false;
    const date1 = new Date(d1.getFullYear(), d1.getMonth(), d1.getDate());
    const date2 = new Date(d2.getFullYear(), d2.getMonth(), d2.getDate());
    return date1 < date2;
  };

  const isBetween = (date, start, end) => {
    if (!start || !end) return false;
    const d = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
    const s = new Date(start.getFullYear(), start.getMonth(), start.getDate()).getTime();
    const e = new Date(end.getFullYear(), end.getMonth(), end.getDate()).getTime();
    return d > s && d < e;
  };

  // Logic Functions
  const drToggle = (forceClose = false) => {
    const isOpen = popover.classList.contains('open');
    if (forceClose || isOpen) {
      popover.classList.remove('show');
      setTimeout(() => popover.classList.remove('open'), 200);
      trigger.classList.remove('active');
    } else {
      popover.classList.add('open');
      // small delay to allow display: flex to apply before opacity transition
      setTimeout(() => popover.classList.add('show'), 10);
      trigger.classList.add('active');
      // Set view to drFrom if present
      if (drFrom) {
        leftDate = new Date(drFrom);
        leftDate.setDate(1);
        rightDate = new Date(leftDate);
        rightDate.setMonth(rightDate.getMonth() + 1);
      }
      drRender();
    }
  };

  const drRenderMonth = (dateObj, containerDiv, labelEl) => {
    labelEl.textContent = formatMonthYear(dateObj);
    containerDiv.innerHTML = '';
    
    const year = dateObj.getFullYear();
    const month = dateObj.getMonth();
    
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0).getDate();
    
    // JS days: 0=Sun, 1=Mon...6=Sat. We want 0=Mon, 1=Tue...6=Sun
    let startDayOfWeek = firstDay.getDay() - 1;
    if (startDayOfWeek === -1) startDayOfWeek = 6;
    
    const today = new Date();

    // Fill empty cells before 1st
    for (let i = 0; i < startDayOfWeek; i++) {
      const cell = document.createElement('div');
      cell.className = 'vdrp-day-cell empty';
      containerDiv.appendChild(cell);
    }
    
    // Create actual days
    for (let d = 1; d <= lastDay; d++) {
      const current = new Date(year, month, d);
      const cell = document.createElement('div');
      cell.className = 'vdrp-day-cell';
      
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'vdrp-day-btn';
      btn.textContent = d;
      
      if (isSameDay(current, today)) {
        cell.classList.add('today');
      }
      
      let isStart = isSameDay(current, drFrom);
      let isEnd = false;
      let isInRange = false;

      if (drFrom && drTo) {
        isEnd = isSameDay(current, drTo);
        if (isBetween(current, drFrom, drTo) || isBetween(current, drTo, drFrom)) {
            isInRange = true;
        }
      } else if (drFrom && drHover) {
        isEnd = isSameDay(current, drHover);
        if (isBetween(current, drFrom, drHover) || isBetween(current, drHover, drFrom)) {
            isInRange = true;
        }
      }

      if (isStart) cell.classList.add('range-start');
      if (isEnd) cell.classList.add('range-end');
      if (isInRange) cell.classList.add('in-range');

      // Mouse events
      btn.addEventListener('mouseenter', () => {
        if (drFrom && !drTo) {
          if (drHover && isSameDay(current, drHover)) return;
          drHover = new Date(current);
          drRender();
        }
      });
      
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        activePreset = null;
        if (!drFrom || (drFrom && drTo)) {
          drFrom = new Date(current);
          drTo = null;
          drHover = null;
        } else if (drFrom && !drTo) {
          let newTo = new Date(current);
          if (isBefore(newTo, drFrom)) {
            drTo = drFrom;
            drFrom = newTo;
          } else {
            drTo = newTo;
          }
          drHover = null;
        }
        drRender();
      });

      cell.appendChild(btn);
      containerDiv.appendChild(cell);
    }
  };

  const drPreset = (key) => {
    activePreset = key;
    const now = new Date();
    now.setHours(0,0,0,0);
    
    switch (key) {
      case 'today':
        drFrom = new Date(now);
        drTo = new Date(now);
        break;
      case 'yesterday':
        drFrom = new Date(now);
        drFrom.setDate(now.getDate() - 1);
        drTo = new Date(drFrom);
        break;
      case 'thisWeek':
        drFrom = new Date(now);
        const day = drFrom.getDay();
        const diff = drFrom.getDate() - day + (day === 0 ? -6 : 1);
        drFrom.setDate(diff);
        drTo = new Date(now);
        break;
      case 'lastWeek':
        const lastWeekEnd = new Date(now);
        const lwDay = lastWeekEnd.getDay();
        lastWeekEnd.setDate(lastWeekEnd.getDate() - lwDay + (lwDay === 0 ? -6 : 1) - 1);
        drFrom = new Date(lastWeekEnd);
        drFrom.setDate(lastWeekEnd.getDate() - 6);
        drTo = new Date(lastWeekEnd);
        break;
      case 'thisMonth':
        drFrom = new Date(now.getFullYear(), now.getMonth(), 1);
        drTo = new Date(now);
        break;
      case 'lastMonth':
        drFrom = new Date(now.getFullYear(), now.getMonth() - 1, 1);
        drTo = new Date(now.getFullYear(), now.getMonth(), 0);
        break;
      case 'last30':
        drFrom = new Date(now);
        drFrom.setDate(now.getDate() - 30);
        drTo = new Date(now);
        break;
      case 'last90':
        drFrom = new Date(now);
        drFrom.setDate(now.getDate() - 90);
        drTo = new Date(now);
        break;
    }
    
    leftDate = new Date(drFrom);
    leftDate.setDate(1);
    rightDate = new Date(leftDate);
    rightDate.setMonth(rightDate.getMonth() + 1);

    drHover = null;
    drRender();
  };

  const drRender = () => {
    drRenderMonth(leftDate, leftDaysContainer, leftLabel);
    drRenderMonth(rightDate, rightDaysContainer, rightLabel);

    if (!drFrom) {
      footerText.textContent = "Selecciona una fecha de inicio";
    } else if (drFrom && !drTo) {
      footerText.textContent = "Selecciona una fecha de fin";
    } else if (drFrom && drTo) {
      if (isSameDay(drFrom, drTo)) {
        footerText.textContent = formatDate(drFrom);
      } else {
        footerText.textContent = `${formatDate(drFrom)} — ${formatDate(drTo)}`;
      }
    }

    if (drFrom && drTo) {
      triggerText.classList.remove('placeholder');
      if (isSameDay(drFrom, drTo)) {
         triggerText.textContent = formatDate(drFrom);
      } else {
         triggerText.textContent = `${formatDate(drFrom)} — ${formatDate(drTo)}`;
      }
      triggerClear.classList.add('visible');
    } else {
      triggerText.classList.add('placeholder');
      triggerText.textContent = "Seleccionar fechas...";
      triggerClear.classList.remove('visible');
    }

    const presetBtns = presetsContainer.querySelectorAll('.vdrp-preset-btn');
    presetBtns.forEach(btn => {
      if (btn.dataset.preset === activePreset) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });
  };

  // Event Listeners
  trigger.addEventListener('click', (e) => {
    if (e.target.closest('.vdrp-trigger-clear')) return;
    drToggle();
  });

  triggerClear.addEventListener('click', (e) => {
    e.stopPropagation();
    drFrom = null;
    drTo = null;
    drHover = null;
    activePreset = null;
    drRender();
    if (options.onChange) {
      options.onChange(null, null);
    }
  });

  const documentClickHandler = (e) => {
    if (!container.contains(e.target)) {
      drToggle(true);
    }
  };
  document.addEventListener('click', documentClickHandler);

  popover.querySelector('.vdrp-prev-month').addEventListener('click', () => {
    leftDate.setMonth(leftDate.getMonth() - 1);
    rightDate.setMonth(rightDate.getMonth() - 1);
    drRender();
  });

  popover.querySelector('.vdrp-next-month').addEventListener('click', () => {
    leftDate.setMonth(leftDate.getMonth() + 1);
    rightDate.setMonth(rightDate.getMonth() + 1);
    drRender();
  });

  popover.querySelector('.vdrp-calendars').addEventListener('mouseleave', () => {
    if (drFrom && !drTo && drHover) {
      drHover = null;
      drRender();
    }
  });

  presetsContainer.addEventListener('click', (e) => {
    if (e.target.classList.contains('vdrp-preset-btn')) {
      drPreset(e.target.dataset.preset);
    }
  });

  popover.querySelector('.vdrp-btn-cancel').addEventListener('click', () => {
    drFrom = null;
    drTo = null;
    drHover = null;
    activePreset = null;
    drRender();
    drToggle(true);
    if (options.onChange) {
      options.onChange(null, null);
    }
  });

  popover.querySelector('.vdrp-btn-apply').addEventListener('click', () => {
    drToggle(true);
    if (options.onChange) {
      options.onChange(drFrom, drTo);
    }
  });

  drRender();

  return {
    getSelection: () => ({ from: drFrom, to: drTo }),
    setSelection: (from, to) => {
      drFrom = from ? new Date(from) : null;
      drTo = to ? new Date(to) : null;
      drRender();
    },
    destroy: () => {
      document.removeEventListener('click', documentClickHandler);
      container.innerHTML = '';
    }
  };
}
