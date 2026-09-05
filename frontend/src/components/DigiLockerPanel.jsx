import { useEffect, useState } from "react";

import {
  startDigiLockerVerification,
  mockDigiLockerVerification,
  getDigiLockerVerification,
} from "../api";


export default function DigiLockerPanel({
  caseId,
  personId,
  personName,
}) {

  const [verification, setVerification] =
    useState(null);

  const [loading, setLoading] =
    useState(false);

  const [error, setError] =
    useState(null);


  // ------------------------------------------------------------
  // Load existing verification
  // ------------------------------------------------------------

  async function loadVerification() {

    if (
      caseId == null ||
      personId == null
    ) {
      return;
    }

    try {

      const result =
        await getDigiLockerVerification(
          caseId,
          personId
        );

      setVerification(
        result.verification
      );

    } catch (err) {

      console.error(
        "Could not load DigiLocker verification:",
        err
      );

    }
  }


  useEffect(() => {

    loadVerification();

  }, [
    caseId,
    personId,
  ]);


  // ------------------------------------------------------------
  // Receive result from DigiLocker popup
  // ------------------------------------------------------------

  useEffect(() => {

    function handleMessage(event) {

      if (
        event.data?.type ===
        "DIGILOCKER_SUCCESS"
      ) {

        setVerification(
          event.data.result
        );

        setLoading(false);

        setError(null);

      }


      if (
        event.data?.type ===
        "DIGILOCKER_ERROR"
      ) {

        setLoading(false);

        setError(
          event.data.description ||
          "DigiLocker authorization failed."
        );

      }

    }


    window.addEventListener(
      "message",
      handleMessage
    );


    return () => {

      window.removeEventListener(
        "message",
        handleMessage
      );

    };

  }, []);


  // ------------------------------------------------------------
  // Start verification
  // ------------------------------------------------------------

  async function verify() {

    if (
      caseId == null ||
      personId == null
    ) {

      setError(
        "Select a PERSON node first."
      );

      return;
    }


    setLoading(true);

    setError(null);


    try {

      const result =
        await startDigiLockerVerification(
          caseId,
          personId
        );


      // --------------------------------------------------------
      // LOCAL MOCK MODE
      // --------------------------------------------------------

      if (
        result.mode === "mock"
      ) {

        const mockResult =
          await mockDigiLockerVerification(
            caseId,
            personId
          );

        setVerification(
          mockResult
        );

        setLoading(false);

        return;
      }


      // --------------------------------------------------------
      // REAL DIGILOCKER MODE
      // --------------------------------------------------------

      const popup =
        window.open(
          result.authorization_url,

          "digilocker",

          [
            "width=600",
            "height=800",
            "resizable=yes",
            "scrollbars=yes",
          ].join(",")
        );


      if (!popup) {

        setError(
          "Popup was blocked. "
          + "Please allow popups for NETRA."
        );

        setLoading(false);

      }

    } catch (err) {

      console.error(
        "DigiLocker verification failed:",
        err
      );

      setError(
        err?.response?.data?.detail ||
        err?.message ||
        "DigiLocker verification failed."
      );

      setLoading(false);

    }

  }


  // ------------------------------------------------------------
  // No PERSON selected
  // ------------------------------------------------------------

  if (
    caseId == null ||
    personId == null
  ) {

    return (
      <article
        className="panel-card identity"
        id="digilockerCard"
      >

        <h2>
          DigiLocker Identity Verification
        </h2>

        <p className="muted">
          Select a PERSON node from the graph
          to perform identity verification.
        </p>

      </article>
    );

  }


  // ------------------------------------------------------------
  // Render
  // ------------------------------------------------------------

  return (

    <article
      className="panel-card identity"
      id="digilockerCard"
    >

      <h2>
        DigiLocker Identity Verification
      </h2>


      <p className="muted">

        Candidate:
        {" "}

        <strong>
          {personName ||
            `PERSON:${personId}`}
        </strong>

      </p>


      {!verification && (

        <div>

          <p className="muted">

            DigiLocker can provide a
            high-confidence identity anchor
            when the required authorization,
            consent and legal access are available.

          </p>


          <button
            type="button"
            className="btn amber"
            onClick={verify}
            disabled={loading}
          >

            {loading
              ? "Waiting for verification..."
              : "Verify with DigiLocker"}

          </button>

        </div>

      )}


      {verification && (

        <div className="item">

          <div>

            <span
              className={
                `badge ${
                  verification.status ===
                    "VERIFIED" ||
                  verification.status ===
                    "VERIFIED_DEMO"
                    ? "ok"
                    : ""
                }`
              }
            >

              {verification.status}

            </span>

          </div>


          <div
            style={{
              marginTop: "8px",
              fontWeight: 700,
            }}
          >

            {verification.verified_name ||
              "Name unavailable"}

          </div>


          <div className="muted">

            Identity confidence:
            {" "}

            {(
              Number(
                verification.confidence || 0
              ) * 100
            ).toFixed(1)}
            %

          </div>


          {verification.name_similarity != null && (

            <div className="muted">

              Name agreement:
              {" "}

              {(
                Number(
                  verification.name_similarity
                ) * 100
              ).toFixed(1)}
              %

            </div>

          )}


          <div className="muted">

            Source:
            {" "}

            {verification.source}

          </div>


          {verification.verified_at && (

            <div className="muted">

              Verified:
              {" "}

              {new Date(
                verification.verified_at
              ).toLocaleString()}

            </div>

          )}


          {verification.message && (

            <div className="muted">

              {verification.message}

            </div>

          )}

        </div>

      )}


      {error && (

        <div
          className="error-inline"
          style={{
            marginTop: "10px",
          }}
        >

          {error}

        </div>

      )}

    </article>

  );
}