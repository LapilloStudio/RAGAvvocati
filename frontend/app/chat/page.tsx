import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import ChatInterface from "@/components/ChatInterface";
import DocumentUpload from "@/components/DocumentUpload";
import FileList from "@/components/FileList";

export default async function ChatPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  return (
    <main className="mx-auto grid min-h-screen max-w-6xl grid-cols-1 gap-6 p-6 lg:grid-cols-3">
      <section className="space-y-6 lg:col-span-1">
        <header>
          <h1 className="text-lg font-semibold">RAGAvvocati</h1>
          <p className="text-sm text-slate-500">{user.email}</p>
        </header>
        <DocumentUpload />
        <FileList />
      </section>
      <section className="lg:col-span-2">
        <ChatInterface />
      </section>
    </main>
  );
}
