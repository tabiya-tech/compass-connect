import React, { useEffect, useState } from "react";
import type { Meta, StoryObj } from "@storybook/react";
import RecordingWaveform from "src/chat/ChatMessageField/recordingWaveform/RecordingWaveform";
import { LEVEL_BARS, LEVEL_SAMPLE_INTERVAL_MS } from "src/speechToText/useSpeechToText";

const meta: Meta<typeof RecordingWaveform> = {
  title: "Chat/ChatMessageField/RecordingWaveform",
  component: RecordingWaveform,
  tags: ["autodocs"],
  decorators: [
    (Story) => (
      <div style={{ padding: 24, maxWidth: 480 }}>
        <Story />
      </div>
    ),
  ],
};

export default meta;

type Story = StoryObj<typeof RecordingWaveform>;

/** Levels that rise and fall like speech, to see the bars move without a microphone. */
const SimulatedRecording: React.FC = () => {
  const [startedAt] = useState(() => Date.now());
  const [levels, setLevels] = useState<number[]>([]);
  useEffect(() => {
    const interval = setInterval(() => {
      const t = Date.now() / 300;
      const level = Math.abs(Math.sin(t) * Math.sin(t / 3.7)) * (0.6 + Math.random() * 0.4);
      setLevels((previous) => [...previous, level].slice(-LEVEL_BARS));
    }, LEVEL_SAMPLE_INTERVAL_MS);
    return () => clearInterval(interval);
  }, []);
  return <RecordingWaveform status="recording" startedAt={startedAt} levels={levels} />;
};

export const Recording: Story = {
  render: () => <SimulatedRecording />,
};

export const RecordingInSilence: Story = {
  args: { status: "recording", startedAt: Date.now(), levels: [] },
};

export const Transcribing: Story = {
  args: { status: "transcribing" },
};
