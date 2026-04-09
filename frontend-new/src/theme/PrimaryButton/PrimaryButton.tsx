import { Button, ButtonProps, Box, useTheme } from "@mui/material";
import { PaletteColor } from "@mui/material/styles";
import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import React, { useContext } from "react";
import { IsOnlineContext } from "src/app/isOnlineProvider/IsOnlineProvider";
import { ComponentError } from "src/error/commonErrors";

interface PrimaryButtonProps extends ButtonProps {
  disableWhenOffline?: boolean;
  showCircle?: boolean;
}

const PrimaryButton: React.FC<PrimaryButtonProps> = ({
  style,
  disabled,
  children,
  disableWhenOffline,
  showCircle = false,
  color = "primary",
  variant = "contained",
  sx,
  ...props
}: Readonly<PrimaryButtonProps>) => {
  const isOnline = useContext(IsOnlineContext);
  const theme = useTheme();

  if (!children) {
    throw new ComponentError("Children are required for PrimaryButton component");
  }

  const cream = theme.palette.common.cream;
  const paletteColor = theme.palette[color as keyof typeof theme.palette] as PaletteColor;
  const isOutlined = variant === "outlined";

  return (
    <Button
      variant={variant}
      color={color}
      style={style}
      sx={{
        borderRadius: "999px",
        fontWeight: 600,
        fontSize: "1rem",
        lineHeight: 1,
        gap: showCircle ? 1.5 : 1,
        justifyContent: showCircle ? "space-between" : "center",
        ...(isOutlined && { border: `2px solid ${paletteColor.main}` }),
        padding: showCircle ? "6px 6px 6px 22px" : "12px 24px",
        "&:focus-visible": {
          outline: `3px solid ${theme.palette.brandAccent.main}`,
          outlineOffset: "2px",
        },
        ...(isOutlined && {
          "&:hover:not(:disabled)": {
            bgcolor: paletteColor.light,
            border: `2px solid ${paletteColor.main}`,
          },
        }),
        "&.Mui-disabled": {
          opacity: 0.38,
          color: isOutlined ? paletteColor.main : paletteColor.contrastText,
          bgcolor: isOutlined ? "transparent" : paletteColor.main,
          ...(isOutlined && { border: `2px solid ${paletteColor.main}` }),
        },
        ...sx,
      }}
      disableElevation
      disabled={Boolean(disabled || (disableWhenOffline && !isOnline))}
      {...props}
    >
      {children}
      {showCircle && (
        <Box
          sx={{
            width: 36,
            height: 36,
            borderRadius: "50%",
            bgcolor: isOutlined ? paletteColor.main : cream,
            color: isOutlined ? cream : paletteColor.main,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          <ArrowForwardIcon sx={{ fontSize: 18 }} />
        </Box>
      )}
    </Button>
  );
};

export default PrimaryButton;
