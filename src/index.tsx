import { callable, definePlugin } from "@decky/api";
import {
  PanelSection, PanelSectionRow, SliderField,
  ButtonItem, ToggleField
} from "@decky/ui";
import { useState, useEffect } from "react";
import { FaBolt } from "react-icons/fa";

declare const SteamClient: {
  GameSessions: {
    RegisterForAppLifetimeNotifications: (cb: (e: {unAppID: number, bRunning: boolean}) => void) => {unregister: () => void};
  };
  System: {
    CopyTextToClipboard: (text: string) => void;
  };
};

declare const appStore: {
  GetAppOverviewByAppID: (appId: number) => { display_name: string } | null;
};

interface Status {
  system_installed: boolean;
  layer_deployed: boolean;
  dll_detected: boolean;
}

interface Settings {
  multiplier: number;
  fps_limit: number;
  flow_scale: number;
  performance_mode: number;
}

const getStatus = callable<[], Status>("get_status");
const getGameSettings = callable<[appId: string], Settings>("get_game_settings");
const saveGameSettings = callable<[appId: string, settings: string], boolean>("save_game_settings");
const getDefaultSettings = callable<[], Settings>("get_default_settings");
const saveDefaultSettings = callable<[settings: string], boolean>("save_default_settings");
const reinstallLayer = callable<[], boolean>("reinstall_layer");
const installRuntime = callable<[], boolean>("install_runtime");
const listGameProfiles = callable<[], string[]>("list_game_profiles");
const downloadLayer = callable<[], {success: boolean, size?: number, error?: string}>("download_layer");

const MULTIPLIER_OPTIONS = [
  { value: 0, label: "OFF" },
  { value: 2, label: "x2" },
  { value: 3, label: "x3" },
  { value: 4, label: "x4" },
];

const state = {
  runningAppId: 0,
  runningGameName: "",
};

interface SettingsControlsProps {
  settings: Settings;
  onChange: (key: keyof Settings, value: number) => void;
}

function SettingsControls({ settings, onChange }: SettingsControlsProps) {
  const multiplierIdx = MULTIPLIER_OPTIONS.findIndex(o => o.value === settings.multiplier);
  const isEnabled = settings.multiplier > 0;
  return (
    <>
      <PanelSectionRow>
        <SliderField
          label="Frame Generation"
          description={MULTIPLIER_OPTIONS[multiplierIdx >= 0 ? multiplierIdx : 0].label}
          value={multiplierIdx >= 0 ? multiplierIdx : 0}
          min={0}
          max={MULTIPLIER_OPTIONS.length - 1}
          step={1}
          notchCount={MULTIPLIER_OPTIONS.length}
          notchLabels={MULTIPLIER_OPTIONS.map((o, i) => ({ notchIndex: i, label: o.label }))}
          onChange={(idx) => onChange("multiplier", MULTIPLIER_OPTIONS[idx].value)}
        />
      </PanelSectionRow>
      {isEnabled && (
        <>
          <PanelSectionRow>
            <SliderField
              label="FPS Limit"
              description={`${settings.fps_limit} → ${settings.fps_limit * settings.multiplier} FPS`}
              value={settings.fps_limit}
              min={15} max={60} step={5}
              onChange={(val) => onChange("fps_limit", val)}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <SliderField
              label="Flow Scale"
              description={`${settings.flow_scale}`}
              value={settings.flow_scale * 10}
              min={1} max={10} step={1}
              onChange={(val) => onChange("flow_scale", val / 10)}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <ToggleField
              label="Performance Mode"
              checked={settings.performance_mode === 1}
              onChange={(checked) => onChange("performance_mode", checked ? 1 : 0)}
            />
          </PanelSectionRow>
        </>
      )}
    </>
  );
}

function copyLaunchOptions() {
  const input = document.createElement('input');
  input.value = '~/lsfg %command%';
  input.style.position = 'absolute';
  input.style.left = '-9999px';
  document.body.appendChild(input);
  input.focus();
  input.select();
  document.execCommand('copy');
  document.body.removeChild(input);
}

function Content() {
  const [status, setStatus] = useState<Status | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [defaults, setDefaults] = useState<Settings | null>(null);
  const [appId, setAppId] = useState(state.runningAppId);
  const [gameName, setGameName] = useState(state.runningGameName);
  const [dirty, setDirty] = useState(false);
  const [reinstalling, setReinstalling] = useState(false);
  const [installProgress, setInstallProgress] = useState("");
  const [profiles, setProfiles] = useState<string[]>([]);
  const [selectedProfile, setSelectedProfile] = useState<string | null>(null);
  const [profileSettings, setProfileSettings] = useState<Settings | null>(null);

  const refresh = async () => {
    const s = await getStatus();
    setStatus(s);
    const d = await getDefaultSettings();
    setDefaults(d);
    const p = await listGameProfiles();
    setProfiles(p);
  };

  const loadGameSettings = async (id: number) => {
    if (id > 0) {
      const cfg = await getGameSettings(String(id));
      setSettings(cfg);
    }
  };

  useEffect(() => {
    refresh();
    if (state.runningAppId > 0) loadGameSettings(state.runningAppId);
    const interval = setInterval(() => {
      if (state.runningAppId !== appId) {
        setAppId(state.runningAppId);
        setGameName(state.runningGameName);
        loadGameSettings(state.runningAppId);
      }
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const updateGameSetting = async (key: keyof Settings, value: number) => {
    if (!settings || appId <= 0) return;
    const updated = { ...settings, [key]: value };
    setSettings(updated);
    setDirty(true);
    await saveGameSettings(String(appId), JSON.stringify(updated));
  };

  const updateDefaultSetting = async (key: keyof Settings, value: number) => {
    if (!defaults) return;
    const updated = { ...defaults, [key]: value };
    setDefaults(updated);
    await saveDefaultSettings(JSON.stringify(updated));
  };

  const handleReinstall = async () => {
    setReinstalling(true);
    await reinstallLayer();
    await refresh();
    setReinstalling(false);
    setDirty(true);
  };

  if (!status) {
    return (
      <PanelSection title="LSFG Frame Gen">
        <PanelSectionRow><div>Loading...</div></PanelSectionRow>
      </PanelSection>
    );
  }

  if (!status.system_installed) {
    return (
      <PanelSection title="LSFG Frame Gen">
        <PanelSectionRow>
          <div style={{ fontSize: "12px" }}>
            LSFG-VK layer not installed.
          </div>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={reinstalling}
            onClick={async () => {
              setReinstalling(true);
              setInstallProgress("Downloading...");
              const dl = await downloadLayer();
              if (!dl.success) {
                setInstallProgress(`Error: ${dl.error}`);
                setReinstalling(false);
                return;
              }
              setInstallProgress("Scheduling deploy...");
              const ok = await installRuntime();
              setReinstalling(false);
              if (ok) {
                setInstallProgress("");
                setDirty(true);
              } else {
                setInstallProgress("Failed to schedule deploy");
              }
            }}
          >
            {reinstalling ? installProgress || "Working..." : dirty ? "Reboot to complete install" : "Install LSFG-VK"}
          </ButtonItem>
        </PanelSectionRow>
        {dirty && (
          <PanelSectionRow>
            <div style={{ fontSize: "11px", color: "#ffaa00" }}>
              Reboot to complete installation.
            </div>
          </PanelSectionRow>
        )}
      </PanelSection>
    );
  }

  // Game running with settings loaded → per-game config
  if (appId > 0 && settings) {
    return (
      <div>
        <PanelSection title={gameName || `App ${appId}`}>
          <SettingsControls settings={settings} onChange={updateGameSetting} />
          {dirty && (
            <PanelSectionRow>
              <div style={{ color: "#ff4444", fontSize: "12px", fontWeight: "bold" }}>
                Restart game for changes to take effect
              </div>
            </PanelSectionRow>
          )}
        </PanelSection>
      </div>
    );
  }

  // No game running → status, default config editor, helpers
  return (
    <div>
      <PanelSection title="LSFG Frame Gen">
        <PanelSectionRow>
          <div style={{ fontSize: "11px", opacity: 0.7 }}>
            {status.layer_deployed
              ? "✓ Layer deployed in FEX RootFS"
              : "⚠ Layer not deployed (try Reinstall Layer)"}
          </div>
        </PanelSectionRow>
        <PanelSectionRow>
          <div style={{ fontSize: "11px", opacity: 0.7 }}>
            {status.dll_detected
              ? "✓ Lossless Scaling installed"
              : "✗ Install Lossless Scaling from Steam"}
          </div>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={copyLaunchOptions}>
            Copy Launch Options
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <div style={{ fontSize: "11px", opacity: 0.5 }}>
            Paste into game Properties → Launch Options
          </div>
        </PanelSectionRow>
      </PanelSection>

      {defaults && (
        <PanelSection title="Default Settings">
          <SettingsControls settings={defaults} onChange={updateDefaultSetting} />
          <PanelSectionRow>
            <div style={{ fontSize: "11px", opacity: 0.5 }}>
              Applied to games without per-game config
            </div>
          </PanelSectionRow>
        </PanelSection>
      )}

      {profiles.length > 0 && (
        <PanelSection title="Game Profiles">
          <PanelSectionRow>
            <SliderField
              label="Select Game"
              description={selectedProfile ? (appStore.GetAppOverviewByAppID(Number(selectedProfile))?.display_name ?? `App ${selectedProfile}`) : "None"}
              value={selectedProfile ? profiles.indexOf(selectedProfile) : -1}
              min={0}
              max={profiles.length - 1}
              step={1}
              notchCount={profiles.length}
              notchLabels={profiles.map((p, i) => ({ notchIndex: i, label: appStore.GetAppOverviewByAppID(Number(p))?.display_name?.substring(0, 8) ?? p }))}
              onChange={async (idx) => {
                const id = profiles[idx];
                setSelectedProfile(id);
                const cfg = await getGameSettings(id);
                setProfileSettings(cfg);
              }}
            />
          </PanelSectionRow>
          {selectedProfile && profileSettings && (
            <SettingsControls settings={profileSettings} onChange={async (key, value) => {
              const updated = { ...profileSettings, [key]: value };
              setProfileSettings(updated);
              await saveGameSettings(selectedProfile, JSON.stringify(updated));
            }} />
          )}
        </PanelSection>
      )}

      <PanelSection title="Maintenance">
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={reinstalling}
            onClick={handleReinstall}
          >
            {reinstalling ? "Downloading..." : dirty ? "Reboot to apply" : "Reinstall Layer"}
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <div style={{ fontSize: "11px", opacity: 0.5 }}>
            Re-deploy layer into FEX RootFS and Proton dirs
          </div>
        </PanelSectionRow>
      </PanelSection>
    </div>
  );
}

export default definePlugin(() => {
  const reg = SteamClient.GameSessions.RegisterForAppLifetimeNotifications((e) => {
    if (e.bRunning) {
      state.runningAppId = e.unAppID;
      const app = appStore.GetAppOverviewByAppID(e.unAppID);
      state.runningGameName = app?.display_name ?? String(e.unAppID);
    } else if (e.unAppID === state.runningAppId) {
      state.runningAppId = 0;
      state.runningGameName = "";
    }
  });

  return {
    name: "LSFG Frame Gen",
    content: <Content />,
    icon: <FaBolt />,
    onDismount() { reg.unregister(); }
  };
});
