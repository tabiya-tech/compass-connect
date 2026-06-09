import { useEffect, useRef, useState } from "react";

export interface UseRefreshGuardResult {
  showConfirmDialog: boolean;
  confirmRefresh: () => void;
  cancelRefresh: () => void;
}

/**
 * When isActive is true, intercepts keyboard refresh shortcuts (F5, Ctrl+R) with a
 * confirm dialog and blocks browser navigation refreshes with beforeunload.
 */
export const useRefreshGuard = (isActive: boolean): UseRefreshGuardResult => {
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const allowRefreshRef = useRef(false);

  useEffect(() => {
    allowRefreshRef.current = false;
    if (!isActive) return;

    // Intercept keyboard shortcuts for refresh (Ctrl+R, F5, etc.)
    const handleKeyDown = (e: KeyboardEvent) => {
      // Check for refresh shortcuts: F5, Ctrl+R, Ctrl+Shift+R
      if (
        !allowRefreshRef.current &&
        (e.key === "F5" ||
          (e.key === "r" && (e.ctrlKey || e.metaKey)) ||
          (e.key === "R" && (e.ctrlKey || e.metaKey) && e.shiftKey))
      ) {
        e.preventDefault();
        e.stopPropagation();
        setShowConfirmDialog(true);
      }
    };

    // Modern browsers ignore custom messages — returnValue is set for legacy support only
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (!allowRefreshRef.current) {
        e.preventDefault();
        e.returnValue = "";
      }
    };

    window.addEventListener("keydown", handleKeyDown, true);
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => {
      window.removeEventListener("keydown", handleKeyDown, true);
      window.removeEventListener("beforeunload", handleBeforeUnload);
      allowRefreshRef.current = false;
    };
  }, [isActive]);

  const confirmRefresh = () => {
    allowRefreshRef.current = true;
    setShowConfirmDialog(false);
    setTimeout(() => window.location.reload(), 0);
  };

  const cancelRefresh = () => setShowConfirmDialog(false);

  return { showConfirmDialog, confirmRefresh, cancelRefresh };
};
