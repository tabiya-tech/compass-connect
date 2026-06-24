import { useEffect } from "react";

/**
 * Updates the browser's theme-color meta tag to match the top section background of the current page.
 * Restores the previous color when the component unmounts (e.g. on route change).
 *
 * @param color - any valid CSS color string, e.g. "#002147" or "rgb(0, 33, 71)"
 */
const useThemeColor = (color: string | undefined) => {
  useEffect(() => {
    if (!color) return;

    const meta = document.querySelector('meta[name="theme-color"]');
    if (!(meta instanceof HTMLMetaElement)) return;

    meta.content = color;

    return () => {
      meta.content = "#fff";
    };
  }, [color]);
};

export default useThemeColor;
