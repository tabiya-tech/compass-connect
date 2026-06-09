import { useEffect, useState } from "react";

export const INACTIVITY_TIMEOUT = 3 * 60 * 1000;
// Check every TIMEOUT + TIMEOUT/3 so worst-case delay is TIMEOUT + one interval
export const CHECK_INACTIVITY_INTERVAL = INACTIVITY_TIMEOUT + INACTIVITY_TIMEOUT / 3;

/**
 * Returns true when the user has been inactive for INACTIVITY_TIMEOUT.
 * Resets automatically on mousedown/keydown events.
 */
export const useInactivityBackdrop = (options: {
  initiallyShown: boolean;
  disabled: boolean;
  conversationCompleted: boolean;
}): boolean => {
  const { initiallyShown, disabled, conversationCompleted } = options;
  const [showBackdrop, setShowBackdrop] = useState(initiallyShown);
  const [lastActivityTime, setLastActivityTime] = useState(Date.now());

  useEffect(() => {
    if (disabled || conversationCompleted) return;

    const checkInactivity = () => {
      if (Date.now() - lastActivityTime > INACTIVITY_TIMEOUT) {
        setShowBackdrop(true);
      }
    };
    const interval = setInterval(checkInactivity, CHECK_INACTIVITY_INTERVAL);
    return () => clearInterval(interval);
  }, [lastActivityTime, disabled, conversationCompleted]);

  useEffect(() => {
    if (disabled) return;

    const resetTimer = () => {
      setLastActivityTime(Date.now());
      setShowBackdrop(false);
    };

    const events = ["mousedown", "keydown"] as const;
    events.forEach((e) => document.addEventListener(e, resetTimer));
    return () => events.forEach((e) => document.removeEventListener(e, resetTimer));
  }, [disabled]);

  return showBackdrop;
};
