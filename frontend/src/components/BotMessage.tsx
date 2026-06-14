import { FeedbackButtons } from "./FeedbackButtons";
import { isRefusal } from "../utils/refusal";
import { formatCitations } from "../utils/citations";

interface Props {
  content: string;
  query: string;
  feature: string;
  sessionId: string;
  repoUrl?: string;
}

export function BotMessage({ content, query, feature, sessionId, repoUrl }: Props) {
  const refusal = isRefusal(content);
  const formatted = formatCitations(content, repoUrl);

  return (
    <div className="flex justify-start mb-4">
      <div className={`rounded-2xl rounded-bl-sm px-4 py-2 max-w-[80%] ${refusal ? "bg-yellow-50 border border-yellow-200" : "bg-gray-100"}`}>
        <div className="text-sm whitespace-pre-wrap">{formatted}</div>
        {!refusal && (
          <FeedbackButtons
            query={query}
            answer={content}
            feature={feature}
            sessionId={sessionId}
          />
        )}
      </div>
    </div>
  );
}
