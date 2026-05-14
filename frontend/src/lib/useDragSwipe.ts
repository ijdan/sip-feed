"use client";
import { useState, useRef } from "react";

interface DragSwipeOptions {
  dismissThreshold?: number;
  readThreshold?: number;
  onDismiss?: () => void;
  onMarkRead?: () => void;
  isRead?: boolean;
}

export interface DragSwipeResult {
  dragX: number;
  dragging: boolean;
  dismissed: boolean;
  swipingLeft: boolean;
  swipingRight: boolean;
  leftProgress: number;
  rightProgress: number;
  handlers: {
    onTouchStart: (e: React.TouchEvent) => void;
    onTouchMove: (e: React.TouchEvent) => void;
    onTouchEnd: () => void;
    onMouseDown: (e: React.MouseEvent) => void;
    onMouseMove: (e: React.MouseEvent) => void;
    onMouseUp: () => void;
    onMouseLeave: () => void;
  };
}

export function useDragSwipe({
  dismissThreshold = 120,
  readThreshold = 100,
  onDismiss,
  onMarkRead,
  isRead = false,
}: DragSwipeOptions = {}): DragSwipeResult {
  const [dragX, setDragX] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [dismissed, setDismissedAnim] = useState(false);
  const startX = useRef(0);

  const triggerDismiss = () => {
    setDismissedAnim(true);
    setTimeout(() => onDismiss?.(), 250);
  };

  const onDragStart = (clientX: number) => { startX.current = clientX; setDragging(true); };
  const onDragMove = (clientX: number) => {
    if (!dragging) return;
    setDragX(clientX - startX.current);
  };
  const onDragEnd = () => {
    if (dragX < -dismissThreshold) triggerDismiss();
    else if (dragX > readThreshold) { onMarkRead?.(); setDragX(0); }
    else setDragX(0);
    setDragging(false);
  };

  const swipingLeft = dragX < -20;
  const swipingRight = dragX > 20;
  const leftProgress = Math.min(1, Math.abs(dragX) / dismissThreshold);
  const rightProgress = Math.min(1, dragX / readThreshold);

  return {
    dragX, dragging, dismissed,
    swipingLeft, swipingRight, leftProgress, rightProgress,
    handlers: {
      onTouchStart: (e) => onDragStart(e.touches[0].clientX),
      onTouchMove: (e) => onDragMove(e.touches[0].clientX),
      onTouchEnd: onDragEnd,
      onMouseDown: (e) => onDragStart(e.clientX),
      onMouseMove: (e) => onDragMove(e.clientX),
      onMouseUp: onDragEnd,
      onMouseLeave: () => { if (dragging) onDragEnd(); },
    },
  };
}
