/**
 * Mocks the html-to-image module so tests that open the feedback modal don't
 * trigger the real DOM-to-canvas pipeline (which calls jsdom-unsupported APIs
 * like getComputedStyle(elt, pseudoElt)).
 * Import this module in any test that renders a component which opens the
 * feedback modal.
 */
jest.mock("html-to-image", () => ({
  __esModule: true,
  toPng: jest.fn().mockResolvedValue("data:image/png;base64,AAAA"),
}));
