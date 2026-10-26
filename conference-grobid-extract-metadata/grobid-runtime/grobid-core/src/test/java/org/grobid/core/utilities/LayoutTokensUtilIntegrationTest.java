package org.grobid.core.utilities;

import static org.hamcrest.CoreMatchers.is;
import static org.junit.Assert.assertThat;

import java.io.File;

import org.junit.BeforeClass;
import org.junit.Test;

import org.grobid.core.document.Document;
import org.grobid.core.document.DocumentSource;
import org.grobid.core.engines.Engine;
import org.grobid.core.engines.config.GrobidAnalysisConfig;
import org.grobid.core.main.LibraryLoader;

public class LayoutTokensUtilIntegrationTest {

    @BeforeClass
    public static void setUp() throws Exception {
        LibraryLoader.load();
        GrobidProperties.getInstance();
    }

    @Test
    public void testDoesRequireDehyphenization2() throws Exception {

        DocumentSource documentSource = DocumentSource
                .fromPdf(new File("src/test/resources/org/grobid/core/utilities/dehypenisation1.pdf"));
        Document result = Engine.getEngine(false)
                .getParsers()
                .getSegmentationParser()
                .processing(documentSource, GrobidAnalysisConfig.defaultInstance());

        assertThat(LayoutTokensUtil.doesRequireDehypenisation(result.getTokenizations(), 7), is(true));

    }

    @Test
    public void testDoesRequireDehyphenization() throws Exception {

        DocumentSource documentSource = DocumentSource
                .fromPdf(new File("src/test/resources/org/grobid/core/utilities/dehypenisation2.pdf"));
        Document result = Engine.getEngine(false)
                .getParsers()
                .getSegmentationParser()
                .processing(documentSource, GrobidAnalysisConfig.defaultInstance());

        assertThat(LayoutTokensUtil.doesRequireDehypenisation(result.getTokenizations(), 7), is(true));

    }

}
