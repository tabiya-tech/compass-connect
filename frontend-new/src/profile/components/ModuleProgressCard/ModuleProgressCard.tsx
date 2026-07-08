import React from "react";
import { Box, Card, CardContent, Typography, LinearProgress, Skeleton, useTheme } from "@mui/material";
import { useTranslation } from "react-i18next";
import type { ProfileStrengthBreakdown } from "src/profile/utils/calculateProfileStrength";
import type { TranslationKey } from "src/react-i18next";

const uniqueId = "module-progress-card-b7e3f4a5-8c9d-1e2f-3a4b-5c6d7e8f9a1b";

export const DATA_TEST_ID = {
  MODULE_PROGRESS_CARD: `module-progress-card-${uniqueId}`,
  MODULE_PROGRESS_TITLE: `module-progress-title-${uniqueId}`,
  MODULE_PROGRESS: (index: number) => `module-progress-${index}-${uniqueId}`,
};

export interface ModuleProgressCardProps {
  profileStrength: ProfileStrengthBreakdown;
  isLoading?: boolean;
}

const COMPONENT_ROWS: { key: keyof Omit<ProfileStrengthBreakdown, "overall">; labelKey: TranslationKey }[] = [
  { key: "experienceCollection", labelKey: "home.profile.profileStrengthExperienceCollection" },
  { key: "skillsDiscovery", labelKey: "home.profile.profileStrengthSkillsDiscovery" },
  { key: "preferences", labelKey: "home.profile.profileStrengthPreferences" },
  { key: "careerReadiness", labelKey: "home.profile.profileStrengthCareerReadiness" },
  { key: "careerExplorer", labelKey: "home.profile.profileStrengthCareerExplorer" },
];

export const ModuleProgressCard: React.FC<ModuleProgressCardProps> = ({ profileStrength, isLoading = false }) => {
  const theme = useTheme();
  const { t } = useTranslation();
  const safeOverallProgress = Math.max(0, Math.min(100, Math.round(profileStrength.overall)));

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: theme.fixedSpacing(theme.tabiyaSpacing.sm) }}>
      <Typography
        variant="h4"
        data-testid={DATA_TEST_ID.MODULE_PROGRESS_TITLE}
        sx={{
          color: theme.palette.text.primary,
          fontWeight: 700,
        }}
      >
        {t("home.profile.profileStrength")}
      </Typography>

      <Card
        sx={{ border: `1px solid ${theme.palette.divider}`, boxShadow: "none" }}
        data-testid={DATA_TEST_ID.MODULE_PROGRESS_CARD}
      >
        <CardContent
          sx={{
            padding: theme.fixedSpacing(theme.tabiyaSpacing.lg),
            "&:last-child": { paddingBottom: theme.fixedSpacing(theme.tabiyaSpacing.lg) },
            display: "flex",
            flexDirection: "column",
            gap: 4,
          }}
        >
          {isLoading ? (
            <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <Skeleton variant="text" width={80} height={40} />
              <Skeleton variant="rectangular" height={12} sx={{ borderRadius: 999 }} />
              {COMPONENT_ROWS.map((row) => (
                <Skeleton key={row.key} variant="rectangular" height={24} sx={{ borderRadius: 999 }} />
              ))}
            </Box>
          ) : (
            <>
              {/* Main Giant Progress */}
              <Box>
                <Typography variant="h5" fontWeight="bold" color="secondary.main">
                  {safeOverallProgress}%
                </Typography>
                <LinearProgress
                  variant="determinate"
                  value={safeOverallProgress}
                  aria-label={t("home.profile.profileStrengthProgressAriaLabel")}
                  data-testid={DATA_TEST_ID.MODULE_PROGRESS(0)}
                  sx={{
                    height: 12,
                    mt: 1,
                    borderRadius: 999,
                    backgroundColor: theme.palette.divider,
                    "& .MuiLinearProgress-bar": { backgroundColor: theme.palette.secondary.main },
                  }}
                />
              </Box>

              {/* Breakdowns */}
              <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
                {COMPONENT_ROWS.map((row, index) => {
                  const { points, max } = profileStrength[row.key];
                  const label = t(row.labelKey);
                  const safeComponentProgress = Math.max(0, Math.min(100, (points / max) * 100));
                  return (
                    <Box
                      key={row.key}
                      sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 1 }}
                    >
                      <Typography variant="body2" color="text.secondary" sx={{ flex: 1 }}>
                        {label}
                      </Typography>
                      <LinearProgress
                        variant="determinate"
                        value={safeComponentProgress}
                        aria-label={t("home.profile.profileStrengthProgressAriaLabel")}
                        data-testid={DATA_TEST_ID.MODULE_PROGRESS(index + 1)}
                        sx={{
                          flex: 1,
                          height: 6,
                          borderRadius: 999,
                          backgroundColor: theme.palette.divider,
                          "& .MuiLinearProgress-bar": {
                            backgroundColor: theme.palette.secondary.main,
                            opacity: 0.6,
                          },
                        }}
                      />
                      <Typography variant="body2" color="text.secondary" fontWeight="bold" sx={{ textAlign: "right" }}>
                        {max}%
                      </Typography>
                    </Box>
                  );
                })}
              </Box>
            </>
          )}
        </CardContent>
      </Card>
    </Box>
  );
};
