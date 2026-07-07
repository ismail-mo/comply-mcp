'use client';

import { useCallback, useRef, useState } from 'react';

interface SplitterProps {
  /** 'left' — dragging right grows the panel (width = start + dx).
   *  'right' — dragging left grows the panel (width = start - dx). */
  side: 'left' | 'right';
  width: number;
  min: number;
  max: number;
  onResize: (width: number) => void;
}

const clamp = (value: number, min: number, max: number): number =>
  Math.min(max, Math.max(min, value));

export function Splitter({ side, width, min, max, onResize }: SplitterProps) {
  const [dragging, setDragging] = useState(false);
  const widthRef = useRef(width);
  widthRef.current = width;

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      const startX = e.clientX;
      const startWidth = widthRef.current;
      setDragging(true);

      const prevCursor = document.body.style.cursor;
      const prevUserSelect = document.body.style.userSelect;
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';

      const handleMouseMove = (ev: MouseEvent) => {
        const dx = ev.clientX - startX;
        const next = side === 'left' ? startWidth + dx : startWidth - dx;
        onResize(clamp(next, min, max));
      };

      const handleMouseUp = () => {
        window.removeEventListener('mousemove', handleMouseMove);
        window.removeEventListener('mouseup', handleMouseUp);
        document.body.style.cursor = prevCursor;
        document.body.style.userSelect = prevUserSelect;
        setDragging(false);
      };

      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
    },
    [side, min, max, onResize]
  );

  return (
    <div
      className={`comply-splitter${dragging ? ' dragging' : ''}`}
      role="separator"
      aria-orientation="vertical"
      onMouseDown={handleMouseDown}
    />
  );
}
