import { notFound } from "next/navigation";
import { ExamSession } from "./ExamSession";

export const metadata = { title: "Test · Recall" };

export default async function TestPaperPage({
  params,
}: PageProps<"/test/[id]">) {
  const { id } = await params;
  const testId = Number(id);
  // Anything can be typed into the address bar; a paper id is an integer.
  if (!Number.isInteger(testId) || testId <= 0) notFound();
  return <ExamSession id={testId} />;
}
