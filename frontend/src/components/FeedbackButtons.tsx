import { useState } from "react";
import { submitFeedback } from "../api/client";

interface Props {
  query: string;
  answer: string;
  feature: string;
  sessionId: string;
}

export function FeedbackButtons({ query, answer, feature, sessionId }: Props) {
  const [submitted, setSubmitted] = useState<"up" | "down" | null>(null);

  const sendFeedback = async (thumbsUp: boolean) => {
    await submitFeedback(query, answer, feature, thumbsUp, sessionId);
    setSubmitted(thumbsUp ? "up" : "down");
  };

  if (submitted) {
    return <span className="text-sm text-gray-500 dark:text-gray-400">Thanks for the feedback!</span>;
  }

  return (
    <div className="flex gap-2 mt-2">
      <button onClick={() => sendFeedback(true)} className="hover:scale-110 transition cursor-pointer">
        👍
      </button>
      <button onClick={() => sendFeedback(false)} className="hover:scale-110 transition cursor-pointer">
        👎
      </button>
    </div>
  );
}
