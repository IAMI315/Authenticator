package com.authenticatordesktop.mobile

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

val AccentBlue = Color(0xFF2878EE)
val FreshGreen = Color(0xFF2B9B59)
val WarmOrange = Color(0xFFF28A2E)
val SoftPurple = Color(0xFF7657D8)
val WindowBackground = Color(0xFFF4F8FD)
val GlassSurface = Color(0xF2FFFFFF)
val GlassMuted = Color(0xFFEFF5FC)
val GlassBorder = Color(0xFFD7E3F2)
val TextPrimary = Color(0xFF172033)
val TextMuted = Color(0xFF68758A)

private val AppColors = lightColorScheme(
    primary = AccentBlue,
    onPrimary = Color.White,
    primaryContainer = Color(0xFFE5F0FF),
    onPrimaryContainer = Color(0xFF164A99),
    secondary = FreshGreen,
    tertiary = SoftPurple,
    background = WindowBackground,
    onBackground = TextPrimary,
    surface = GlassSurface,
    onSurface = TextPrimary,
    surfaceVariant = GlassMuted,
    onSurfaceVariant = TextMuted,
    outline = GlassBorder,
    error = Color(0xFFD43D3D),
)

@Composable
fun AuthenticatorTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = AppColors, content = content)
}
