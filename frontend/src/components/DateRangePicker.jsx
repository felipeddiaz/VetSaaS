import { useEffect, useRef } from 'react';
import { initDateRangePicker } from './VanillaDateRangePicker/VanillaDateRangePicker';

export default function DateRangePicker({ from, to, onChange, placeholder = "Seleccionar fechas..." }) {
  const containerRef = useRef(null);
  const pickerRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // Initialize the Vanilla JS picker
    pickerRef.current = initDateRangePicker(containerRef.current, {
      initialFrom: from,
      initialTo: to,
      onChange: (newFrom, newTo) => {
        // Format to YYYY-MM-DD for the parent component
        const formatDate = (date) => {
          if (!date) return "";
          const d = new Date(date);
          const year = d.getFullYear();
          const month = String(d.getMonth() + 1).padStart(2, '0');
          const day = String(d.getDate()).padStart(2, '0');
          return `${year}-${month}-${day}`;
        };
        
        onChange(formatDate(newFrom), formatDate(newTo));
      }
    });

    // We can access the internal trigger text to set the custom placeholder
    // although the vanilla JS uses a hardcoded one by default.
    const triggerText = containerRef.current.querySelector('.vdrp-trigger-text');
    if (triggerText && !from && !to) {
        triggerText.textContent = placeholder;
    }

    return () => {
      if (pickerRef.current) {
        pickerRef.current.destroy();
      }
    };
  }, []); // Empty dependency array means it initializes once

  // Sync external prop changes into the picker if needed
  useEffect(() => {
    if (pickerRef.current) {
        // We only want to set selection if the parent strictly clears it.
        // It's tricky to sync bidirectional state with a vanilla component easily,
        // but checking if both are empty allows 'Clear Filters' to work.
        if (!from && !to) {
             const current = pickerRef.current.getSelection();
             if (current.from || current.to) {
                 pickerRef.current.setSelection(null, null);
                 const triggerText = containerRef.current.querySelector('.vdrp-trigger-text');
                 if (triggerText) triggerText.textContent = placeholder;
             }
        }
    }
  }, [from, to, placeholder]);

  return <div ref={containerRef} style={{ display: 'inline-block' }}></div>;
};