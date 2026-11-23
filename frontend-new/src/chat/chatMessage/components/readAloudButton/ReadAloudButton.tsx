import React from "react";
import VolumeUpOutlinedIcon from "@mui/icons-material/VolumeUpOutlined";
import StopCircleOutlinedIcon from "@mui/icons-material/StopCircleOutlined";
import { CircularProgress, useTheme } from "@mui/material";
import { useTranslation } from "react-i18next";
import PrimaryIconButton from "src/theme/PrimaryIconButton/PrimaryIconButton";
import { useReadAloud } from "src/textToSpeech/ReadAloudContext";

const uniqueId = "a3c7e4f1-8d2b-4e6a-9f0c-b5d1e2a3f4c6";

export const DATA_TEST_ID = {
  READ_ALOUD_BUTTON: `read-aloud-button-${uniqueId}`,
  READ_ALOUD_ICON: `read-aloud-icon-${uniqueId}`,
  STOP_READING_ICON: `stop-reading-icon-${uniqueId}`,
  LOADING_ICON: `loading-icon-${uniqueId}`,
};

export interface ReadAloudButtonProps {
  /** The id of the message, to know whether it is the one being read. */
  messageId: string;
  /** The markdown of the message. */
  message: string;
}

/**
 * Reads an AI message aloud, and stops it. Renders nothing when read aloud is not offered in the current locale.
 */
const ReadAloudButton: React.FC<ReadAloudButtonProps> = ({ messageId, message }) => {
  const { t } = useTranslation();
  const theme = useTheme();
  const player = useReadAloud();

  if (!player) return null;

  const { state } = player;
  const isThisMessage = state.status !== "idle" && state.messageId === messageId;
  const isLoading = isThisMessage && state.status === "loading";
  const isPlaying = isThisMessage && state.status === "playing";

  const handleClick = () => {
    if (isLoading || isPlaying) {
      player.stop();
    } else {
      player.play(messageId, message);
    }
  };

  const label = isLoading
    ? t("chat.readAloud.loadingAriaLabel")
    : isPlaying
      ? t("chat.readAloud.stopReadingAriaLabel")
      : t("chat.readAloud.readAloudAriaLabel");
  const iconSize = theme.fixedSpacing(theme.tabiyaSpacing.lg);

  return (
    <PrimaryIconButton
      data-testid={DATA_TEST_ID.READ_ALOUD_BUTTON}
      onClick={handleClick}
      title={label}
      aria-label={label}
      aria-pressed={isLoading || isPlaying}
      sx={{ color: isPlaying ? theme.palette.primary.main : theme.palette.text.secondary }}
    >
      {isLoading ? (
        <CircularProgress
          data-testid={DATA_TEST_ID.LOADING_ICON}
          size={iconSize}
          sx={{ color: theme.palette.text.secondary }}
        />
      ) : isPlaying ? (
        <StopCircleOutlinedIcon data-testid={DATA_TEST_ID.STOP_READING_ICON} sx={{ fontSize: iconSize }} />
      ) : (
        <VolumeUpOutlinedIcon data-testid={DATA_TEST_ID.READ_ALOUD_ICON} sx={{ fontSize: iconSize }} />
      )}
    </PrimaryIconButton>
  );
};

export default ReadAloudButton;
