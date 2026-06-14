import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Box, Container, Typography, useTheme } from "@mui/material";
import MarkdownReader from "src/knowledgeHub/components/MarkdownReader/MarkdownReader";
import { getDarkLogoUrl, getLogoUrl, getProductName } from "src/envService";
import { getLegalDocument, LegalDocument } from "src/legal/legalDocumentLoader";
import type { LegalDocumentVariant } from "src/legal/legalDocumentLoader";
import { routerPaths } from "src/app/routerPaths";
import { Backdrop } from "src/theme/Backdrop/Backdrop";
import ErrorPage from "src/error/errorPage/ErrorPage";

const uniqueId = "b2c9e1a4-6f3d-4b8e-9c2a-1d5e7f0a4b6c";

export const DATA_TEST_ID = {
  LEGAL_PAGE_CONTAINER: `legal-page-container-${uniqueId}`,
  LEGAL_PAGE_LOGO: `legal-page-logo-${uniqueId}`,
  LEGAL_PAGE_TITLE: `legal-page-title-${uniqueId}`,
  LEGAL_PAGE_BODY: `legal-page-body-${uniqueId}`,
};

export interface LegalDocumentPageProps {
  variant: LegalDocumentVariant;
}

const LegalDocumentPage: React.FC<LegalDocumentPageProps> = ({ variant }) => {
  const theme = useTheme();
  const { t } = useTranslation();
  const appName = getProductName() || "Njila";

  const [document, setDocument] = useState<LegalDocument | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [hasError, setHasError] = useState<boolean>(false);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setHasError(false);
    setDocument(null);

    getLegalDocument(variant)
      .then((doc) => {
        if (cancelled) return;
        setDocument(doc);
      })
      .catch((error) => {
        if (cancelled) return;
        console.error(`Failed to load legal document for variant "${variant}":`, error);
        setHasError(true);
      })
      .finally(() => {
        if (cancelled) return;
        setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [variant]);

  if (hasError) {
    return <ErrorPage errorMessage={t("legal.documentUnavailable")} showRefreshButton />;
  }

  if (isLoading || !document) {
    return <Backdrop isShown={true} />;
  }

  const logoUrlFromEnv = getDarkLogoUrl() || getLogoUrl();
  const logoSrc = logoUrlFromEnv || `${process.env.PUBLIC_URL}/njila-logo-dark.svg`;

  return (
    <Box
      component="main"
      data-testid={DATA_TEST_ID.LEGAL_PAGE_CONTAINER}
      sx={{
        minHeight: "100vh",
        backgroundColor: theme.palette.pageBackground.main,
        py: theme.spacing(theme.tabiyaSpacing.lg),
        px: "var(--layout-gutter-x)",
      }}
    >
      <Container
        maxWidth="md"
        sx={{
          display: "flex",
          flexDirection: "column",
          gap: theme.spacing(theme.tabiyaSpacing.md),
        }}
      >
        <Link to={routerPaths.ROOT} aria-label="Go back">
          <Box
            component="img"
            src={logoSrc}
            alt={appName}
            data-testid={DATA_TEST_ID.LEGAL_PAGE_LOGO}
            sx={{ maxWidth: "70%", width: "auto", height: "auto", objectFit: "contain", alignSelf: "flex-start" }}
          />
        </Link>

        <Typography variant="h2" textAlign="center" data-testid={DATA_TEST_ID.LEGAL_PAGE_TITLE}>
          {document.title}
        </Typography>

        <Box data-testid={DATA_TEST_ID.LEGAL_PAGE_BODY}>
          <MarkdownReader content={document.markdown} headingEmphasis />
        </Box>
      </Container>
    </Box>
  );
};

export default LegalDocumentPage;
