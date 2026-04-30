import { useEffect, useState } from "react";

function App() {
  const [clients, setClients] = useState([]);
  const [selectedClient, setSelectedClient] = useState(null);
  const [search, setSearch] = useState("");

  // 🔹 Charger les clients
  const loadClients = () => {
    fetch("http://127.0.0.1:5000/clients")
      .then(res => res.json())
      .then(data => setClients(data));
  };

  useEffect(() => {
    loadClients();
  }, []);

  // 🔍 Recherche
  const handleSearch = () => {
    fetch(`http://127.0.0.1:5000/search?nom=${search}`)
      .then(res => res.json())
      .then(data => setClients(data));
  };

  return (
    <div style={{ padding: "20px", fontFamily: "Arial" }}>
      <h1>📊 CRM Clients</h1>

      {/* 🔍 Recherche */}
      <input
        placeholder="Rechercher un client"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        style={{ marginRight: "10px" }}
      />
      <button onClick={handleSearch}>Rechercher</button>
      <button onClick={loadClients} style={{ marginLeft: "10px" }}>
        Reset
      </button>

      {/* ➕ Ajouter client */}
      <button
        style={{
          marginLeft: "20px",
          background: "green",
          color: "white",
          padding: "8px",
          border: "none",
          cursor: "pointer"
        }}
        onClick={() =>
          window.open(
            "https://forms.fillout.com/t/m3LqBsmhP7us",
            "_blank"
          )
        }
      >
        ➕ Ajouter un client
      </button>

      {/* 📋 Tableau */}
      <table
        border="1"
        cellPadding="10"
        style={{ marginTop: "20px", width: "100%" }}
      >
        <thead>
          <tr>
            <th>Nom</th>
            <th>CA</th>
            <th>Activité</th>
            <th>Actions</th>
          </tr>
        </thead>

        <tbody>
          {clients.map((c) => (
            <tr key={c.id}>
              {/* 🔥 NOM */}
              <td>{c["nom client"] || "-"}</td>

              {/* 🔥 CA (gestion tableau) */}
              <td>
                {Array.isArray(c["CA"])
                  ? c["CA"][0]
                  : c["CA"] || "-"}
              </td>

              {/* 🔥 ACTIVITÉ */}
              <td>{c["activite R"] || "-"}</td>

              <td>
                {/* 👁️ Voir */}
                <button onClick={() => setSelectedClient(c)}>
                  👁️ Voir
                </button>

                {/* ✏️ Modifier */}
                {c["Lien modification"] && (
                  <button
                    style={{ marginLeft: "10px" }}
                    onClick={() =>
                      window.open(c["Lien modification"], "_blank")
                    }
                  >
                    ✏️ Modifier
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* 🔥 POPUP DETAIL */}
      {selectedClient && (
        <div
          style={{
            position: "fixed",
            top: "10%",
            left: "25%",
            width: "50%",
            background: "white",
            padding: "20px",
            border: "2px solid black",
            boxShadow: "0px 0px 10px rgba(0,0,0,0.3)"
          }}
        >
          <h2>📋 Détail client</h2>

          {Object.entries(selectedClient).map(([key, value]) => (
            <div key={key}>
              <strong>{key} :</strong>{" "}
              {Array.isArray(value)
                ? value[0]
                : typeof value === "object"
                ? JSON.stringify(value)
                : value?.toString()}
            </div>
          ))}

          <button
            style={{ marginTop: "20px" }}
            onClick={() => setSelectedClient(null)}
          >
            Fermer
          </button>
        </div>
      )}
    </div>
  );
}

export default App;