import { splitIntoParts, toPlainText } from "./plainText";

describe("toPlainText", () => {
  test.each([
    ["a link", "Read [the guide](https://example.org/guide) first.", "Read the guide first."],
    ["a bare link", "See https://example.org/jobs?x=1 for more.", "See for more."],
    [
      "bold and italic text",
      "This is **very** important, *really* and __truly__.",
      "This is very important, really and truly.",
    ],
    ["struck text", "It is ~~not~~ done.", "It is not done."],
    ["inline code", "Type `hello` to start.", "Type hello to start."],
    ["a code block", "Run this:\n```bash\nnpm start\n```", "Run this: npm start."],
    ["a heading", "## Your skills\nYou can cook.", "Your skills. You can cook."],
    ["a quote", "> Keep going", "Keep going."],
    ["an image", "Look: ![a happy worker](https://example.org/a.png)", "Look: a happy worker."],
    ["html", "Line<br/>two <b>bold</b>", "Line. two bold."],
    ["emoji", "Great job! 🎉👏🏽 Let's continue 👩‍🔧.", "Great job! Let's continue ."],
  ])("should strip %s", (_d, givenMarkdown, expectedText) => {
    // GIVEN a message with markdown
    // WHEN it is turned into plain text
    const actualText = toPlainText(givenMarkdown);
    // THEN expect the text to read, without the markdown
    expect(actualText).toBe(expectedText);
  });

  test("should read each item of a list as a sentence", () => {
    // GIVEN a message with a bulleted and a numbered list
    const givenMarkdown = "Your skills:\n- Cooking\n* Cleaning\n\n1. Driving\n2) Selling!";

    // WHEN it is turned into plain text
    const actualText = toPlainText(givenMarkdown);

    // THEN expect the items without their markers, each ending a sentence
    expect(actualText).toBe("Your skills: Cooking. Cleaning. Driving. Selling!");
  });

  test("should drop the markers of a table and its rules", () => {
    // GIVEN a message with a table and a horizontal rule
    const givenMarkdown = "| Job | Years |\n|---|:---:|\n| Cook | 3 |\n\n---\nDone";

    // WHEN it is turned into plain text
    const actualText = toPlainText(givenMarkdown);

    // THEN expect the cells as text
    expect(actualText).toBe("Job Years. Cook 3. Done.");
  });

  test("should keep a plain message as it is", () => {
    // GIVEN a message without markdown
    const givenMarkdown = "Tell me about your last job, and what you did there.";
    // WHEN it is turned into plain text
    // THEN expect the same text
    expect(toPlainText(givenMarkdown)).toBe(givenMarkdown);
  });

  test("should keep asterisks and underscores that are not emphasis", () => {
    // GIVEN a message with a product of numbers and a snake_case word
    const givenMarkdown = "It costs 2 * 3 dollars at my_shop.";
    // WHEN it is turned into plain text
    // THEN expect them to be kept
    expect(toPlainText(givenMarkdown)).toBe(givenMarkdown);
  });
});

describe("splitIntoParts", () => {
  const utf8Length = (text: string) => new TextEncoder().encode(text).length;

  test("should keep a short text in one part", () => {
    // GIVEN a text within the limit
    const givenText = "One sentence. Another one.";
    // WHEN it is split
    // THEN expect one part
    expect(splitIntoParts(givenText, 100)).toEqual([givenText]);
  });

  test("should split a long text at sentence boundaries, in order", () => {
    // GIVEN three sentences, each within the limit, but not two together
    const givenSentences = ["First sentence is here.", "Second one follows it!", "Is this the third one?"];
    const givenLimit = 30;

    // WHEN the text is split
    const actualParts = splitIntoParts(givenSentences.join(" "), givenLimit);

    // THEN expect one sentence per part, in order
    expect(actualParts).toEqual(givenSentences);
  });

  test("should group sentences that fit together", () => {
    // GIVEN short sentences
    const givenText = "A b. C d. E f. G h.";

    // WHEN the text is split with a limit that fits two sentences
    const actualParts = splitIntoParts(givenText, 10);

    // THEN expect two sentences per part
    expect(actualParts).toEqual(["A b. C d.", "E f. G h."]);
  });

  test("should split a sentence longer than the limit at spaces", () => {
    // GIVEN a sentence longer than the limit
    const givenText = "one two three four five six seven eight";

    // WHEN it is split
    const actualParts = splitIntoParts(givenText, 10);

    // THEN expect every part within the limit
    actualParts.forEach((part) => expect(utf8Length(part)).toBeLessThanOrEqual(10));
    // AND the parts to make up the whole text, in order
    expect(actualParts.join(" ")).toBe(givenText);
  });

  test("should count the limit in bytes of UTF-8, without breaking characters", () => {
    // GIVEN a word of two-byte and four-byte characters longer than the limit
    const givenText = "ééééé𝄞𝄞";

    // WHEN it is split with a limit of 4 bytes
    const actualParts = splitIntoParts(givenText, 4);

    // THEN expect every part within the limit
    actualParts.forEach((part) => expect(utf8Length(part)).toBeLessThanOrEqual(4));
    // AND the characters to be whole, in order
    expect(actualParts.join("")).toBe(givenText);
  });

  test("should give no part for an empty text", () => {
    // GIVEN an empty text
    // WHEN it is split
    // THEN expect no part
    expect(splitIntoParts("   ", 100)).toEqual([]);
  });
});
