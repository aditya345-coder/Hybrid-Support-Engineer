export function isRefusal(answer: string): boolean {
  const a = (answer || "").toLowerCase();
  return a.includes("as an ai specialized") && a.includes("i cannot provide information");
}
