import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';

export type VoiceState = 'idle' | 'listening' | 'processing';

const noop = () => {};

interface UseVoiceReturn {
  voiceState: VoiceState;
  startRecording: () => void;
  stopRecording: () => void;
  abortRecording: () => void;
}

/**
 * Custom hook for voice-to-text recording and transcription.
 *
 * @param onTranscription - Called with transcribed text after successful recording.
 * @param enabled - When false, returns idle state and noop callbacks (safe to call unconditionally).
 */
export function useVoice(
  onTranscription: (text: string) => void,
  enabled: boolean,
): UseVoiceReturn {
  const [voiceState, setVoiceState] = useState<VoiceState>('idle');
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const mimeTypeRef = useRef<string>('audio/webm');

  // Ref to avoid stale closure in async onstop callback
  const onTranscriptionRef = useRef(onTranscription);
  onTranscriptionRef.current = onTranscription;

  // Cleanup on unmount -- stop recording and release mic
  useEffect(() => {
    return () => {
      if (mediaRecorderRef.current?.state === 'recording') {
        mediaRecorderRef.current.stop();
      }
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  const transcribe = useCallback(async (blob: Blob): Promise<string> => {
    const formData = new FormData();
    formData.append('file', blob, 'recording.webm');
    const res = await fetch('/api/audio/transcribe', {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(
        (data as { error?: string }).error || 'Transcription failed',
      );
    }
    const { text } = (await res.json()) as { text: string };
    return text;
  }, []);

  const startRecording = useCallback(async () => {
    try {
      console.log('[voice] Recording started');
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];
      const mimeType = MediaRecorder.isTypeSupported('audio/webm')
        ? 'audio/webm'
        : 'audio/mp4';
      mimeTypeRef.current = mimeType;
      const mediaRecorder = new MediaRecorder(stream, { mimeType });
      mediaRecorderRef.current = mediaRecorder;
      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      mediaRecorder.start();
      setVoiceState('listening');
    } catch (err) {
      console.error('[voice] Microphone access denied', err);
      toast.error('Microphone access denied');
    }
  }, []);

  const stopRecording = useCallback(() => {
    const mr = mediaRecorderRef.current;
    const stream = streamRef.current;
    if (!mr || mr.state !== 'recording') return;
    mr.stop();
    stream?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    mediaRecorderRef.current = null;

    mr.onstop = async () => {
      setVoiceState('processing');
      const blob = new Blob(chunksRef.current, { type: mimeTypeRef.current });
      console.log(
        '[voice] Recording stopped, transcribing, blob size=',
        blob.size,
      );
      try {
        const text = await transcribe(blob);
        console.log('[voice] Transcription success, length=', text.length);
        setVoiceState('idle');
        if (text.trim()) onTranscriptionRef.current(text);
        else console.log('[voice] Empty transcription, not submitting');
      } catch (err) {
        console.error('[voice] Transcription failed', err);
        toast.error('Transcription failed');
        setVoiceState('idle');
      }
    };
  }, [transcribe]);

  const abortRecording = useCallback(() => {
    const mr = mediaRecorderRef.current;
    const stream = streamRef.current;
    if (!mr || mr.state !== 'recording') return;
    mr.onstop = () => setVoiceState('idle');
    mr.stop();
    stream?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    mediaRecorderRef.current = null;
  }, []);

  if (!enabled) {
    return {
      voiceState: 'idle',
      startRecording: noop,
      stopRecording: noop,
      abortRecording: noop,
    };
  }

  return { voiceState, startRecording, stopRecording, abortRecording };
}
