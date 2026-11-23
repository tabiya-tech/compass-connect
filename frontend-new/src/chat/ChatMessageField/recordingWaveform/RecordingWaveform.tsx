import React, { useEffect, useRef, useState } from "react";
import { Box, CircularProgress, keyframes, Typography, useMediaQuery, useTheme } from "@mui/material";
import { useTranslation } from "react-i18next";
import { LEVEL_BARS } from "src/speechToText/useSpeechToText";

const uniqueId = "5b0f6c2e-7a41-4c39-9d8e-3f2a1b6c4d70";

export const DATA_TEST_ID = {
  RECORDING_WAVEFORM: `recording-waveform-${uniqueId}`,
  RECORDING_WAVEFORM_BAR: `recording-waveform-bar-${uniqueId}`,
  RECORDING_STATIC_INDICATOR: `recording-static-indicator-${uniqueId}`,
  RECORDING_ELAPSED_TIME: `recording-elapsed-time-${uniqueId}`,
  RECORDING_TRANSCRIBING: `recording-transcribing-${uniqueId}`,
  RECORDING_ANNOUNCEMENT: `recording-announcement-${uniqueId}`,
};

export const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

const BAR_WIDTH_PX = 3;
const BAR_GAP_PX = 2;
/** How many bars are shown until the width of the graph is known (and in tests, which have no layout). */
export const DEFAULT_VISIBLE_BARS = 32;

const pulse = keyframes`
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
`;

/** As many bars as fit in the width of the element, so the graph fills the field at any screen size. */
const useVisibleBars = (element: React.RefObject<HTMLElement>): number => {
  const [count, setCount] = useState(DEFAULT_VISIBLE_BARS);
  useEffect(() => {
    const node = element.current;
    if (!node || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      const width = entry.contentRect.width;
      if (width > 0) {
        setCount(Math.min(LEVEL_BARS, Math.max(1, Math.floor((width + BAR_GAP_PX) / (BAR_WIDTH_PX + BAR_GAP_PX)))));
      }
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [element]);
  return count;
};

export type RecordingWaveformProps =
  | {
      status: "recording";
      /** When the recording started, in milliseconds since the epoch. */
      startedAt: number;
      /** The latest audio levels, oldest first, from 0 to 1. */
      levels: number[];
    }
  | { status: "transcribing" };

/** Read by screen readers only. */
const visuallyHidden = {
  position: "absolute",
  width: 1,
  height: 1,
  overflow: "hidden",
  clip: "rect(0 0 0 0)",
  whiteSpace: "nowrap",
} as const;

const formatElapsed = (elapsedMs: number): string => {
  const totalSeconds = Math.max(0, Math.floor(elapsedMs / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
};

const ElapsedTime: React.FC<{ startedAt: number }> = ({ startedAt }) => {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(interval);
  }, []);
  return (
    <Typography
      variant="body2"
      data-testid={DATA_TEST_ID.RECORDING_ELAPSED_TIME}
      sx={{ fontVariantNumeric: "tabular-nums" }}
    >
      {formatElapsed(now - startedAt)}
    </Typography>
  );
};

const LevelBars: React.FC<{ levels: number[]; height: string; color: string }> = ({ levels, height, color }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const visibleBars = useVisibleBars(containerRef);
  return (
    <Box
      ref={containerRef}
      aria-hidden
      sx={{
        display: "flex",
        alignItems: "center",
        justifyContent: "flex-end",
        gap: `${BAR_GAP_PX}px`,
        flex: 1,
        minWidth: 0,
        height,
        overflow: "hidden",
      }}
    >
      {Array.from({ length: visibleBars }, (_, index) => {
        // the newest level is on the right, as in a voice note; before there is enough history, the bars are silent
        const level = levels[levels.length - visibleBars + index] ?? 0;
        return (
          <Box
            key={index}
            data-testid={DATA_TEST_ID.RECORDING_WAVEFORM_BAR}
            data-level={level.toFixed(2)}
            sx={{
              flexShrink: 0,
              width: BAR_WIDTH_PX,
              minHeight: BAR_WIDTH_PX,
              borderRadius: BAR_WIDTH_PX,
              height: `${Math.round(level * 100)}%`,
              backgroundColor: color,
              transition: "height 100ms linear",
            }}
          />
        );
      })}
    </Box>
  );
};

/**
 * Shown in the message field while the user records: bars that follow the voice, and the elapsed time. Then, while
 * the recording is transcribed, a short "transcribing" state. With reduced motion, a static indicator replaces the bars.
 */
const RecordingWaveform: React.FC<RecordingWaveformProps> = (props) => {
  const { t } = useTranslation();
  const theme = useTheme();
  const prefersReducedMotion = useMediaQuery(REDUCED_MOTION_QUERY);
  const barHeight = theme.fixedSpacing(theme.tabiyaSpacing.lg);

  const announcement =
    props.status === "recording" ? t("chat.voiceInput.recording") : t("chat.voiceInput.transcribing");

  return (
    <Box
      data-testid={DATA_TEST_ID.RECORDING_WAVEFORM}
      sx={{
        display: "flex",
        alignItems: "center",
        gap: theme.fixedSpacing(theme.tabiyaSpacing.sm),
        width: "100%",
        minHeight: barHeight,
        color: theme.palette.text.secondary,
      }}
    >
      <Box
        component="span"
        role="status"
        aria-live="polite"
        data-testid={DATA_TEST_ID.RECORDING_ANNOUNCEMENT}
        sx={visuallyHidden}
      >
        {announcement}
      </Box>
      {props.status === "recording" ? (
        <>
          {!prefersReducedMotion && (
            <Box
              aria-hidden
              sx={{
                flexShrink: 0,
                width: 8,
                height: 8,
                borderRadius: "50%",
                backgroundColor: theme.palette.error.main,
                animation: `${pulse} 1.2s ease-in-out infinite`,
              }}
            />
          )}
          {prefersReducedMotion ? (
            <Box
              data-testid={DATA_TEST_ID.RECORDING_STATIC_INDICATOR}
              aria-hidden
              sx={{ display: "flex", alignItems: "center", gap: theme.fixedSpacing(theme.tabiyaSpacing.xs), flex: 1 }}
            >
              <Box sx={{ width: 10, height: 10, borderRadius: "50%", backgroundColor: theme.palette.error.main }} />
              <Typography variant="body2">{t("chat.voiceInput.recording")}</Typography>
            </Box>
          ) : (
            <LevelBars levels={props.levels} height={barHeight} color={theme.palette.error.main} />
          )}
          <ElapsedTime startedAt={props.startedAt} />
        </>
      ) : (
        <Box
          data-testid={DATA_TEST_ID.RECORDING_TRANSCRIBING}
          sx={{ display: "flex", alignItems: "center", gap: theme.fixedSpacing(theme.tabiyaSpacing.xs) }}
        >
          {/* hidden from assistive technologies: the status above says that the recording is being transcribed */}
          <CircularProgress aria-hidden size={16} sx={{ color: theme.palette.text.secondary }} />
          <Typography variant="body2">{t("chat.voiceInput.transcribing")}</Typography>
        </Box>
      )}
    </Box>
  );
};

export default RecordingWaveform;
