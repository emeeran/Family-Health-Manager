import { useState } from "react";
import { useParams } from "react-router-dom";
import { Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Sparkles, AlertTriangle } from "lucide-react";
import { generateInsight } from "@/lib/api/ai";
import type { AIInsightResponse } from "@/lib/types/ai";

export default function AIPage() {
  const { memberId } = useParams<{ memberId: string }>();
  const [prompt, setPrompt] = useState("");
  const [healthRecordId, setHealthRecordId] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AIInsightResponse | null>(null);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!prompt.trim()) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const response = await generateInsight({
        prompt: prompt.trim(),
        health_record_id: healthRecordId.trim() || null,
      });
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate insight");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Link to="/members" className="hover:underline">
          Members
        </Link>
        <span>/</span>
        <Link to={`/members/${memberId}`} className="hover:underline">
          Member
        </Link>
        <span>/</span>
        <span className="text-foreground">AI Assistant</span>
      </div>
      <div className="flex items-center gap-2">
        <Sparkles className="h-6 w-6" />
        <h1 className="text-2xl font-bold">AI Health Assistant</h1>
      </div>
      <Alert>
        <AlertTriangle className="h-4 w-4" />
        <AlertDescription>
          This is not medical advice. Consult a healthcare professional for any medical concerns.
        </AlertDescription>
      </Alert>
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">Ask a Question</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="prompt">Your Question</Label>
              <Textarea
                id="prompt"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                rows={4}
                placeholder="e.g., What do my latest lab results indicate?"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="health_record_id">Health Record ID (optional)</Label>
              <Input
                id="health_record_id"
                value={healthRecordId}
                onChange={(e) => setHealthRecordId(e.target.value)}
                placeholder="Link to a specific health record"
              />
            </div>
            <Button type="submit" disabled={loading || !prompt.trim()}>
              {loading ? "Generating..." : "Generate Insight"}
            </Button>
          </form>
        </CardContent>
      </Card>
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {result && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">AI Response</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <p className="text-sm font-medium mb-1">Your Question:</p>
              <p className="text-sm text-muted-foreground">{result.prompt}</p>
            </div>
            <div>
              <p className="text-sm font-medium mb-1">Response:</p>
              <p className="text-sm whitespace-pre-wrap">{result.response}</p>
            </div>
            <div className="text-xs text-muted-foreground space-y-1">
              <p>Provider: {result.provider_used}</p>
              <p>Generated: {new Date(result.generated_at).toLocaleString()}</p>
              <p className="italic">{result.disclaimer}</p>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
