import React from "react";
import VolumeUpOutlinedIcon from "@mui/icons-material/VolumeUpOutlined";
import StopCircleOutlinedIcon from "@mui/icons-material/StopCircleOutlined";
import { CircularProgress, useTheme } from "@mui/material";
import { useTranslation } from "react-i18next";
import PrimaryIconButton from "src/theme/PrimaryIconButton/PrimaryIconButton";
import { getTextToSpeechEnabled } from "src/envService";
import { useTextToSpeech } from "src/textToSpeech/useTextToSpeech";

const uniqueId = "a3c7e4f1-8d2b-4e6a-9f0c-b5d1e2a3f4c6";

export const DATA_TEST_ID = {
  READ_ALOUD_BUTTON: `read-aloud-button-${uniqueId}`,
  READ_ALOUD_ICON: `read-aloud-icon-${uniqueId}`,
  STOP_READING_ICON: `stop-reading-icon-${uniqueId}`,
  LOADING_ICON: `loading-icon-${uniqueId}`,
};

interface ReadAloudButtonProps {
  messageText: string;
}

const ReadAloudButton: React.FC<ReadAloudButtonProps> = ({ messageText }) => {
  const { t } = useTranslation();
  const theme = useTheme();
  const isTtsEnabled = getTextToSpeechEnabled().toLowerCase() === "true";
  const { status, speak, stop, isSupported } = useTextToSpeech();

  if (!isTtsEnabled || !isSupported) return null;

  const isPlaying = status === "playing";
  const isLoading = status === "loading";

  const handleClick = () => {
    if (isPlaying || isLoading) {
      stop();
    } else {
      speak(messageText);
    }
  };

  const getTooltip = () => {
    if (isLoading) return t("chat.textToSpeech.loadingTooltip");
    if (isPlaying) return t("chat.textToSpeech.stopReadingTooltip");
    return t("chat.textToSpeech.readAloudTooltip");
  };

  const renderIcon = () => {
    const iconSize = theme.fixedSpacing(theme.tabiyaSpacing.lg);

    if (isLoading) {
      return (
        <CircularProgress
          data-testid={DATA_TEST_ID.LOADING_ICON}
          size={iconSize}
          sx={{ color: theme.palette.text.secondary }}
        />
      );
    }
    if (isPlaying) {
      return <StopCircleOutlinedIcon data-testid={DATA_TEST_ID.STOP_READING_ICON} sx={{ fontSize: iconSize }} />;
    }
    return <VolumeUpOutlinedIcon data-testid={DATA_TEST_ID.READ_ALOUD_ICON} sx={{ fontSize: iconSize }} />;
  };

  return (
    <PrimaryIconButton
      data-testid={DATA_TEST_ID.READ_ALOUD_BUTTON}
      onClick={handleClick}
      disabled={isLoading}
      title={getTooltip()}
      sx={{
        alignSelf: "flex-end",
        color: isPlaying ? theme.palette.primary.main : theme.palette.text.secondary,
      }}
    >
      {renderIcon()}
    </PrimaryIconButton>
  );
};

export default ReadAloudButton;
