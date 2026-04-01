const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

type EmailPayload = {
  to?: string;
  subject?: string;
  text?: string;
  metadata?: Record<string, unknown>;
};

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const resendApiKey = Deno.env.get("RESEND_API_KEY");
    const senderEmail = Deno.env.get("SENDER_EMAIL");

    if (!resendApiKey || !senderEmail) {
      return new Response(
        JSON.stringify({ error: "Missing RESEND_API_KEY or SENDER_EMAIL secret." }),
        {
          status: 500,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        },
      );
    }

    const body = (await req.json()) as EmailPayload;
    if (!body.to || !body.subject || !body.text) {
      return new Response(
        JSON.stringify({ error: "Expected to, subject, and text fields." }),
        {
          status: 400,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        },
      );
    }

    const resendResponse = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${resendApiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        from: senderEmail,
        to: [body.to],
        subject: body.subject,
        text: body.text,
        tags: body.metadata
          ? Object.entries(body.metadata)
              .filter(([, value]) => value != null)
              .slice(0, 10)
              .map(([name, value]) => ({ name, value: String(value) }))
          : undefined,
      }),
    });

    const resendPayload = await resendResponse.text();
    if (!resendResponse.ok) {
      return new Response(
        JSON.stringify({
          error: "Resend request failed.",
          detail: resendPayload,
        }),
        {
          status: 502,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        },
      );
    }

    return new Response(
      JSON.stringify({ ok: true, provider_response: resendPayload }),
      {
        status: 200,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      },
    );
  } catch (error) {
    return new Response(
      JSON.stringify({
        error: "Unhandled send-standby-email failure.",
        detail: error instanceof Error ? error.message : String(error),
      }),
      {
        status: 500,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      },
    );
  }
});
