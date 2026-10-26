import React from "react";
import { Box, Button, Typography, useTheme } from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import { useTranslation } from "react-i18next";

export interface ReturnToPlatformBannerProps {
  /** Where the user came from, as stored by the integration API. Must pass getReturnSite. */
  returnUrl: string;
}

const uniqueId = "5e0b7c2a-9d41-4f6e-8a3b-2c1d0e9f7a64";

export const DATA_TEST_ID = {
  CONTAINER: `return-to-platform-banner-container-${uniqueId}`,
  BUTTON: `return-to-platform-banner-button-${uniqueId}`,
};

/**
 * The hostname to show for a return URL, or null when the URL must not be followed.
 * The backend only stores allowed origins; this re-checks the scheme as a second guard (no javascript: or data:).
 */
export const getReturnSite = (returnUrl: string | null | undefined): string | null => {
  if (!returnUrl) return null;
  try {
    const url = new URL(returnUrl);
    return url.protocol === "https:" || url.protocol === "http:" ? url.hostname : null;
  } catch {
    return null;
  }
};

/**
 * Shown at the bottom of the skills conversation once it completes, for a user created by another platform.
 * Sends the user back to that platform, in the same tab. Takes the place of the "continue with the next module"
 * banner: for these users the way back comes first.
 */
const ReturnToPlatformBanner: React.FC<ReturnToPlatformBannerProps> = ({ returnUrl }) => {
  const theme = useTheme();
  const { t } = useTranslation();
  const site = getReturnSite(returnUrl);

  if (!site) return null;

  return (
    <Box
      data-testid={DATA_TEST_ID.CONTAINER}
      sx={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: theme.spacing(theme.tabiyaSpacing.sm),
        padding: theme.spacing(theme.tabiyaSpacing.md),
        borderTop: `1px solid ${theme.palette.divider}`,
      }}
    >
      <Typography variant="body2" color="text.secondary" textAlign="center">
        {t("chat.handoffReturn.message", { site })}
      </Typography>
      <Button
        variant="contained"
        startIcon={<ArrowBackIcon />}
        onClick={() => window.location.assign(returnUrl)}
        data-testid={DATA_TEST_ID.BUTTON}
        sx={{ textTransform: "none" }}
      >
        {t("chat.handoffReturn.backTo", { site })}
      </Button>
    </Box>
  );
};

export default ReturnToPlatformBanner;
