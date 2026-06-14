interface Props {
  content: string;
}

export function UserMessage({ content }: Props) {
  return (
    <div className="flex justify-end mb-4">
      <div className="bg-blue-600 text-white rounded-2xl rounded-br-sm px-4 py-2 max-w-[80%]">
        <p className="text-sm">{content}</p>
      </div>
    </div>
  );
}
